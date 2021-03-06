import decimal
import rtyaml

from django.conf import settings
from django.utils.timezone import now

from contrib.de import DemocracyEngineAPIClient, HumanReadableValidationError, DummyDemocracyEngineAPIClient

# Make a singleton instance of the DE client.
if settings.DE_API:
	DemocracyEngineAPI = DemocracyEngineAPIClient(
		settings.DE_API['api_baseurl'],
		settings.DE_API['account_number'],
		settings.DE_API['username'],
		settings.DE_API['password'],
		settings.DE_API['fees-recipient-id'],
		)
else:
	# Testing only, obviously!
	import os
	if "NO_DE" not in os.environ:
		print("Using DummyDemocracyEngineAPI!!")
	DemocracyEngineAPI = DummyDemocracyEngineAPIClient()

def create_de_donation_basic_dict(pledge):
	# Creates basic info for a Democracy Engine API call for creating
	# a transaction (both authtest and auth+capture calls) based on a
	# Pledge instance and its ContributorInfo profile.
	return {
		"donor_first_name": pledge.profile.extra['contributor']['contribNameFirst'],
		"donor_last_name": pledge.profile.extra['contributor']['contribNameLast'],
		"donor_address1": pledge.profile.extra['contributor']['contribAddress'],
		"donor_city": pledge.profile.extra['contributor']['contribCity'],
		"donor_state": pledge.profile.extra['contributor']['contribState'],
		"donor_zip": pledge.profile.extra['contributor']['contribZip'],

		# Campaigns like to sign up the user to their mail list. Since
		# we make lots of microcontributions, we got users signed up
		# to dozens of mail lists unexpectedly. Don't pass the email
		# to DE so that DE doesn't pass it on to campaigns.
		#"donor_email": pledge.get_email(),

		"compliance_employer": pledge.profile.extra['contributor']['contribEmployer'],
		"compliance_occupation": pledge.profile.extra['contributor']['contribOccupation'],

		"email_opt_in": False,
		"is_corporate_contribution": False,

		# use contributor info as billing info in the hopes that it might
		# reduce DE's merchant fees, and maybe we'll get back CC verification
		# info that might help us with data quality checks in the future?
		"cc_first_name": pledge.profile.extra['contributor']['contribNameFirst'],
		"cc_last_name": pledge.profile.extra['contributor']['contribNameLast'],
		"cc_zip": pledge.profile.extra['contributor']['contribZip'],
	}

def run_authorization_test(pledge, ccnum, cccvc, aux_data):
	# Runs an authorization test at the time the user is making a pledge,
	# which tests the card info and also gets a credit card token that
	# can be used later to make a real charge without other billing
	# details.

	# Logging.
	aux_data.update({
		"trigger": pledge.trigger.id,
		"campaign": pledge.via_campaign.id,
		"pledge": pledge.id,
		"user": pledge.user.id if pledge.user else 0,
		"email": pledge.user.email if pledge.user else pledge.anon_user.email,
		"pledge_created": pledge.created,
	})

	# Basic contributor details.
	de_don_req = create_de_donation_basic_dict(pledge)

	# Add billing details.
	de_don_req.update({
		"authtest_request":  True,
		"token_request": True,

		# billing details
		"cc_number": ccnum,
		"cc_month": pledge.profile.extra['billing']['cc_exp_month'],
		"cc_year": pledge.profile.extra['billing']['cc_exp_year'],
		"cc_verification_value": cccvc,

		# no line items are necessary for an authorization test
		"line_items": [],

		# tracking info, which for an auth test stays private?
		"source_code": "itfsite pledge auth", 
		"ref_code": "", 
		"aux_data": rtyaml.dump(aux_data), # DE will gives this back to us encoded as YAML, but the dict encoding is ruby-ish so to be sure we can parse it, we'll encode it first
		})

	# Perform the authorization test and return the transaction record.
	#
	#   a) This tests that the billing info is valid.
	#   b) We get a token that we can use on future transactions so that we
	#      do not need to collect the credit card info again.
	de_txn = DemocracyEngineAPI.create_donation(de_don_req)

	# Store the transaction authorization, which contains the credit card token,
	# into the pledge.
	pledge.profile.extra['billing']['authorization'] = de_txn
	pledge.profile.extra['billing']['de_cc_token'] = de_txn['token']

def get_pledge_recipient_breakdown(trigger):
	# Compute how many recipients there are in each category for a hypothetical
	# pledge.

	if trigger.extra and "subtriggers" in trigger.extra:
		# This is a super-trigger. Add together the recipients for the subtriggers.
		from contrib.models import Trigger
		counts = [{ } for outcome in trigger.outcomes]
		for rec in trigger.extra["subtriggers"]:
			inner_counts = get_pledge_recipient_breakdown_simple(Trigger.objects.get(id=rec["trigger"]))
			for (super_outcome_index, sub_outcome_index) in enumerate(rec["outcome-map"]):
				for key, count in inner_counts[sub_outcome_index].items():
					counts[super_outcome_index][key] = counts[super_outcome_index].get(key, 0) + count

	else:
		# This is a regular Trigger.
		counts = get_pledge_recipient_breakdown_simple(trigger)

	return [ [ { "incumbent": key[0], "party": key[1], "count": count }
	           for key, count
	           in outcome_counts.items() ]
	         for outcome_counts in counts ]

def get_pledge_recipient_breakdown_simple(trigger):
	counts = [{ } for outcome in trigger.outcomes]

	if len(trigger.outcomes) != 2: raise ValueError("counting assumes two outcomes")

	for action in trigger.execution.actions.all().select_related('actor'):
		# Actor did not take a counted action.
		if action.outcome is None: continue

		# Actor is no longer able to take contributions.
		if action.actor.inactive_reason: continue

		for outcome in range(len(trigger.outcomes)):
			if action.outcome == outcome:
				# incumbent and the actor's party
				key = (1, action.party.name[0])
			else:
				if action.actor.challenger is None: # should always be present but in testing...
					if settings.DEBUG:
						continue # don't warn
					else:
						raise ValueError("Missing challenger for %s." % str(action.actor))
				# challenger and the challenger's party
				key = (-1, action.actor.challenger.party.name[0])
			counts[outcome][key] = counts[outcome].get(key, 0) + 1

	return counts

def get_pledge_recipients(pledge):
	# For pledge execution, figure out how to split the contribution
	# across actual recipients.
	#
	# This function returns a list of tuples of recipient information.
	# The pledge amount is going to be evenly split across the list elements.
	#
	# Note that some Pledges yield Actions from multiple Triggers. In that
	# case we may return a list with repeated (non-unique) recipients, but
	# each entry across a single recipient will have a different Action.
	#
	# We also use this during Pledge creation
	# validation, when the trigger is already executed, so we can
	# stop the user from making a Pledge that will have no recipients.
	# In that case, pledge may be an unsaved Pledge instance.

	from contrib.models import Trigger, ActorParty, Actor, Action, Recipient, ContributionRecipientType

	# What trigger(s) does this Pledge execute actions from?
	if not pledge.extra or not pledge.extra.get("triggers"):
		# The usual case is that the Pledge uses the Actions of its Trigger.
		# There is only one desired outcome, but we make a simple mapping to it.
		triggers = [pledge.trigger]
		desired_outcome = { pledge.trigger.id: pledge.desired_outcome }
		error_descr = lambda action : str(pledge)

	else:
		# If the extra.triggers key is specified, then it is a list of
		# pairs of trigger IDs and desired outcomes.
		desired_outcome = dict(pledge.extra["triggers"])

		# And this Pledge uses the Actions listed for the executions of those triggers
		# rather than its own trigger.
		triggers = Trigger.objects.in_bulk(desired_outcome.keys())

		# For error messages...
		error_descr = lambda action : str(action) + " for " + str(pledge)

	# What Actions occurred as a part of all of these triggers?
	actions = Action.objects\
		.filter(execution__trigger__in=triggers)\
		.prefetch_related('actor', 'actor__challenger', 'execution')

	# Build the recipient list.

	recipients = []

	for action in actions:
		# Skip actions with null outcomes, meaning the Actor didn't really
		# take an action and so no contribution for or against is made.

		if action.outcome is None:
			continue

		# Skip Actions where the Actor is no longer able to receive contributions.
		# Although we normally null-out the outcome field in corresponding Actions
		# (and so we would skip per the statement above), when a pledge is made on
		# a trigger that was executed a long time ago, circumstances may have changed.
		# If the incumbent can't take contributions, we don't give to an opponent
		# either.
		if action.actor.inactive_reason:
			continue

		# Get recipient_type and the Recipient object.

		if action.outcome == desired_outcome[action.execution.trigger_id]:
			# The incumbent did what the user wanted, so the incumbent is the recipient.

			# Get what sort of recipient this is.
			recipient_type = ContributionRecipientType.Incumbent

			# Get the Recipient object.
			try:
				r = Recipient.objects.get(actor=action.actor)
			except Recipient.DoesNotExist:
				if settings.DEBUG:
					continue
				raise Recipient.DoesNotExist("There is no recipient for " + str(action.actor) + " while executing " + error_descr(action) + ".")

		else:
			# The incumbent did something other than what the user wanted, so the
			# challenger of the opposite party is the recipient.
			#
			# Use the Actor's current challenger at the time this function is called.
			# That might be different from the challenger at the time the Trigger was
			# executed.

			# Get what sort of recipient this is.
			recipient_type = ContributionRecipientType.GeneralChallenger

			# Get the Recipient object.
			r = action.actor.challenger
			if not r:
				# We don't have a challenger Recipient associated. There should always
				# be a challenger Recipient assigned.
				if settings.DEBUG:
					continue
				raise Recipient.DoesNotExist(str(action.actor) + " has no challenger recipient assigned, while executing " + error_descr(action) + ".")

		# The Recipient may not be currently taking contributions.
		# This condition should be filtered out earlier in the creation
		# of Action objects --- it should have a null outcome with
		# explanation.
		
		if not r.active:
			raise ValueError("Recipient is inactive: %s => %s" % (action, r))

		# Filter if the pledge is for incumbents or for challengers only.

		if recipient_type == ContributionRecipientType.Incumbent \
			 and pledge.incumb_challgr == -1:
			continue
		if recipient_type == ContributionRecipientType.GeneralChallenger \
			 and pledge.incumb_challgr == 1:
			continue

		# Filter by party.

		if pledge.filter_party is not None and r.party != pledge.filter_party:
			continue

		# If we got here, then r is an acceptable recipient.
		recipients.append( (action, recipient_type, r) )

	return recipients

def compute_charge(pledge, recipients):
	# Return a tuple of:
	#  * a list of (recipient, action, amount) line items
	#  * the fees line-item amount
	#  * the total charge

	from contrib.models import Pledge

	# What's the total amount of contributions after fess? The inputs
	# here are all decimal.Decimal instances, so we are doing exact
	# decimal math up to the default precision.
	fees_fixed = Pledge.current_algorithm()['fees_fixed']
	fees_percent = Pledge.current_algorithm()['fees_percent']
	max_contrib = (pledge.amount - fees_fixed) / (1 + fees_percent)
	if max_contrib < decimal.Decimal('0.01'):
		raise HumanReadableValidationError("The amount is less than the minimum fees.")

	# If we divide that evenly among the recipients, what is the ideal contribution?
	# Round it down to the nearest cent because we can only make whole-cent contributions
	# and contributions must be equal and the total must not exceed the original amount.
	recip_contrib = max_contrib / len(recipients)
	recip_contrib = recip_contrib.quantize(decimal.Decimal('.01'), rounding=decimal.ROUND_DOWN)
	if recip_contrib < decimal.Decimal('0.01'):
		# The pledge amount was so small that we can't divide it.
		# This should never happen because our minimum pledge is
		# more than one cent for each potential recipient for a
		# Trigger.
		raise HumanReadableValidationError("The amount is not enough to divide evenly across %d recipients." % len(recipients))

	# Make a list of line items.
	recip_contribs = [(action, recipient_type, recipient, recip_contrib) for (action, recipient_type, recipient) in recipients]

	# Multiply out to create the total before fees.
	contrib_total = len(recipients) * recip_contrib

	# Compute the total with fees. Rather than computing the fees first
	# and hoping the total is under the original pledge amount (the
	# maximum), compute the total, round, clip at the ceiling, and then
	# work backwards to the fees.
	total_charge = contrib_total * (1 + fees_percent) + fees_fixed

	# Round to the nearest cent, then ensure we haven't exeeded maximum.
	total_charge = total_charge.quantize(decimal.Decimal('.01'), rounding=decimal.ROUND_HALF_EVEN)
	if total_charge > pledge.amount:
		total_charge = pledge.amount

	# Fees are the difference between the total and the contributions.
	fees = total_charge - contrib_total

	# Return!
	return (recip_contribs, fees, total_charge)

def create_pledge_donation(pledge, recipients):
	# Pledge execution --- make a credit card charge and return
	# the DE donation record and other details.

	# Compute the amount to charge the user. We can only make whole-penny
	# contributions, so the exact amount of the charge may be less than
	# what the user pledged. recip_contribs is the line item amounts for
	# each recipient as a tuple of (recipient, action, amount).
	recip_contribs, fees, total_charge = compute_charge(pledge, recipients)

	# Prepare line items for the API.
	line_items = []

	# Create the line item for fees.
	line_items.append({
		"recipient_id": DemocracyEngineAPI.fees_recipient_id,
		"amount": DemocracyEngineAPI.format_decimal(fees),
		})

	# Create the line items for campaign recipients.
	for action, recipient_type, recipient, amount in recip_contribs:
		line_items.append({
			"recipient_id": recipient.de_id,
			"amount": DemocracyEngineAPI.format_decimal(amount),
			})

	# Prepare the donation record for authorization & capture.
	de_don_req = create_de_donation_basic_dict(pledge)
	de_don_req.update({
		# billing info
		"token": pledge.profile.extra['billing']['de_cc_token'],

		# line items
		"line_items": line_items,

		# reported to the recipient
		"source_code": "",
		"ref_code": "",

		# tracking info for internal use
		"aux_data": rtyaml.dump({ # DE will gives this back to us encoded as YAML, but the dict encoding is ruby-ish so to be sure we can parse it, we'll encode it first
			"trigger": pledge.trigger.id,
			"campaign": pledge.via_campaign.id,
			"pledge": pledge.id,
			"user": pledge.user.id if pledge.user else None,
			"email": pledge.get_email(),
			"pledge_created": pledge.created,
			})
		})

	# Sanity check the total.
	if sum(decimal.Decimal(li['amount'].replace("$", "")) for li in de_don_req['line_items']) \
		!= total_charge:
		raise ValueError("Sum of line items does not match total charge.")
	
	# Create the 'donation', which creates a transaction and performs cc authorization.
	don = DemocracyEngineAPI.create_donation(de_don_req)

	# Return.
	return (recip_contribs, fees, total_charge, don)

def void_pledge_transaction(txn_guid, allow_credit=False):
	# This raises a 404 exception if the transaction info is not
	# yet available.
	txn = DemocracyEngineAPI.get_transaction(txn_guid)

	# Prepare some return status information.
	ret = {
		"txn": txn,
		"timestamp": now().isoformat(),
	}

	if txn['status'] in ("voided", "credited"):
		# We are good.
		return ret

	if txn['status'] not in ("authorized", "captured"):
		raise ValueError("Not sure what to do with a transaction with status %s." % txn['status'])

	# Attempt void.
	try:
		resp = DemocracyEngineAPI.void_transaction(txn_guid)
		ret["action"] = "void"
	except HumanReadableValidationError as e:
		# Void failed.

		# The transaction exists but is not captured yet, so
		# we can't do anything.
		if str(e) == "please wait until the transaction has captured before voiding or crediting":
			raise

		# Try credit.
		ret["void_error"] = str(e)
		try:
			if not allow_credit:
				raise
			resp = DemocracyEngineAPI.credit_transaction(txn_guid)
			ret["action"] = "credit"
		except Exception as e1:
			raise ValueError("Could not void & credit transaction. Void: %s | Credit: %s"
				% (str(e), str(e1)))

	return ret

