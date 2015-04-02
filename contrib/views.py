from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseForbidden, Http404
from django.conf import settings

from twostream.decorators import anonymous_view, user_view_for

from contrib.models import Trigger, TriggerStatus, TriggerExecution, ContributorInfo, Pledge, PledgeStatus, PledgeExecution, Contribution, ActorParty, ContributionAggregate, IncompletePledge
from contrib.utils import json_response
from contrib.bizlogic import HumanReadableValidationError, run_authorization_test

import copy
import rtyaml
import random

# Used by unit tests to override the suggested pledge.
SUGGESTED_PLEDGE_AMOUNT = None

@anonymous_view
def trigger(request, id, slug):
	# get the object
	trigger = get_object_or_404(Trigger, id=id)

	# redirect to canonical URL if slug does not match
	if trigger.slug != slug:
		return redirect(trigger.get_absolute_url())

	# Defaults. Note that these are also used for triggers that have been executed
	# but for which there were no pledges that resulted in transactions, so use
	# zeros instead of None's where needed.

	outcomes = None
	actions = None
	avg_pledge = 0
	avg_contrib = 0
	num_contribs = None
	num_recips = 0
	num_actors = 0
	by_incumb_chlngr = []

	try:
		te = trigger.execution
	except TriggerExecution.DoesNotExist:
		te = None

	if te and te.pledge_count_with_contribs > 0 and te.pledge_count >= .75 * trigger.pledge_count:
		# Get the contribution aggregates by outcome and sort by total amount of contributions.
		outcomes = te.get_outcomes()

		# Actions/Actors. Sort with actors that received no contributions either for or against at
		# the end of the list, since they're sort of no-data rows. After that, sort by the sum of
		# the contributions plus the negative of the contributions to their challengers. For ties,
		# sort alphabetically on name.
		actions = list(te.actions.all().select_related('actor'))
		actions.sort(key = lambda a : (
			a.outcome is None, # non-voting actors at the end
			(a.total_contributions_for + a.total_contributions_against) == 0, # no contribs either way at end
			-(a.total_contributions_for - a.total_contributions_against), # sort by contribs for minus contribs against
			a.reason_for_no_outcome, # among non-voting actors, sort by the reason
			a.outcome, # among voting actors, group by vote
			a.actor.name_sort # finally, by last name
			)
		)
		num_recips = 0
		num_actors = 0
		for a in actions:
			if a.total_contributions_for > 0: num_recips += 1
			if a.total_contributions_against > 0: num_recips += 1
			if a.total_contributions_for > 0 or a.total_contributions_against > 0: num_actors += 1

		# Incumbent/challengers.
		by_incumb_chlngr = [["Incumbent", 0, "text-success"], ["Opponent", 0, "text-danger"]]
		for a in actions:
			by_incumb_chlngr[0][1] += a.total_contributions_for
			by_incumb_chlngr[1][1] += a.total_contributions_against

		# Compute other summary stats.
		num_contribs = te.num_contributions
		avg_pledge = te.total_contributions / te.pledge_count_with_contribs
		avg_contrib = te.total_contributions / num_contribs
	else:
		# If the trigger has been executed but not enough pledges
		# have completed being executed yet, then pretend like
		# nothing has been executed.
		te = None

	return render(request, "contrib/trigger.html", {
		"trigger": trigger,
		"execution": te,
		"outcomes": outcomes,
		"alg": Pledge.current_algorithm(),
		"min_contrib": trigger.get_minimum_pledge(),
		"suggested_pledge": SUGGESTED_PLEDGE_AMOUNT or random.choice([5, 10]),
		
		"actions": actions,
		"by_incumb_chlngr": by_incumb_chlngr,
		"avg_pledge": avg_pledge,
		"num_contribs": num_contribs,
		"num_recips": num_recips,
		"num_actors": num_actors,
		"avg_contrib": avg_contrib,
	})

def get_user_pledges(user, request):
	# Returns the Pledges that a user owns as a QuerySet.
	if user and user.is_authenticated():
		return Pledge.objects.filter(user=user)
	elif request.session.get('anon_pledge_created'):
		return Pledge.objects.filter(id__in=request.session.get('anon_pledge_created'))
	else:
		return Pledge.objects.none() # empty QuerySet

@user_view_for(trigger)
def trigger_user_view(request, id, slug):
	trigger = get_object_or_404(Trigger, id=id)
	ret = { }

	# Most recent pledge info so we can fill in defaults on the user's next pledge.
	ret["pledge_defaults"] = get_recent_pledge_defaults(request.user, request)

	# Get the user's pledge, if any, on this trigger.
	p = get_user_pledges(request.user, request).filter(trigger=trigger).first()

	if p:
		# The user already made a pledge on this. Render another template
		# to show what the user's pledge was (and how it was executed, if
		# it was.)
		import django.template
		template = django.template.loader.get_template("contrib/contrib.html")
		pe = PledgeExecution.objects.filter(pledge=p).first()
		contribs = sorted(Contribution.objects.filter(pledge_execution=pe).select_related("action"), key=lambda c : (c.recipient.is_challenger, c.action.name_sort))

		# Also include recommendations for further actions.
		recs = []
		for t in Trigger.objects.filter(status=TriggerStatus.Open).order_by('-total_pledged'):
			# Not something the user already took action on (including this pledge!).
			if p.user is not None and t.pledges.filter(user=p.user).exists(): continue
			if p.email is not None and t.pledges.filter(email=p.email).exists(): continue
			# Get up to three.
			recs.append(t)
			if len(recs) == 3:
				break

		ret["pledge_made"] = template.render(django.template.Context({
			"trigger": trigger,
			"pledge": p,
			"execution": pe,
			"contribs": contribs,
			"recommendations": recs,
			"url": request.build_absolute_uri(trigger.get_absolute_url()),
		}))

	return ret

@require_http_methods(['POST'])
@json_response
def get_user_defaults(request):
	# Get the user's past contributor information to pre-populate fields.
	# We avoid doing an actual login here because login() changes the
	# CSRF token, and a mid-page token change will cause future AJAX
	# requests to fail.

	# authenticate
	from itfsite.accounts import User
	from itfsite.betteruser import LoginException
	try:
		user = User.authenticate(request.POST['email'].strip(), request.POST['password'].strip())
	except LoginException as e:
		return { "status": "NotValid", "message": str(e) }

	# check that the user hasn't already done this
	trigger = Trigger.objects.get(id=request.POST['trigger'])
	if trigger.pledges.filter(user=user).exists():
		return { "status": "AlreadyPledged" }

	# get recent data
	return get_recent_pledge_defaults(user, request)

def get_recent_pledge_defaults(user, request):
	# Return a dictionary of information submitted with the user's most recent pledge
	# so that we can pre-fill form fields.

	ret = { }

	# Get the user's most recent Pledge. If the user has no Pledges,
	# just return the empty dict.
	pledges = get_user_pledges(user, request)
	pledge = pledges.order_by('-created').first()
	if not pledge:
		return ret

	# How many open pledges does this user already have?
	ret['open_pledges'] = pledges.filter(status=PledgeStatus.Open).count()

	# Copy Pledge fields.
	for field in ('email', 'amount', 'incumb_challgr', 'filter_party', 'filter_competitive'):
		ret[field] = getattr(pledge, field)
		if type(ret[field]).__name__ == "Decimal":
			ret[field] = float(ret[field])
		elif isinstance(ret[field], ActorParty):
			ret[field] = str(ret[field])

	# Copy contributor fields from the profile's extra dict.
	for field in ('contribNameFirst', 'contribNameLast', 'contribAddress', 'contribCity', 'contribState', 'contribZip',
		'contribOccupation', 'contribEmployer'):
		ret[field] = pledge.profile.extra['contributor'][field]

	# Return a summary of billing info to show how we would bill.
	ret['cclastfour'] = pledge.profile.cclastfour

	# And indicate which pledge we're sourcing this from so that in
	# the submit view we can retreive it again without having to
	# pass it back from the (untrusted) client.
	ret['from_pledge'] = pledge.id

	return ret

# Validates the email address a new user is providing during
# the pledge (user says they have no password). Returns a
# ValidateEmailResult as text, e.g. "ValidateEmailResult.Valid".
# Also record every email address users enter so we can follow-up
# if the user did not finish the pledge form.
@csrf_exempt # for testing via curl
@require_http_methods(["POST"])
def validate_email(request):
	from itfsite.models import User
	from itfsite.betteruser import validate_email, ValidateEmailResult

	email = request.POST['email'].strip()
	ret = validate_email(email)

	if ret == ValidateEmailResult.Valid and not User.objects.filter(email=email).exists():
		# Store for later, if this is not a user already with an account.
		# Only have at most one of these records per trigger-email address pair.
		IncompletePledge.objects.get_or_create(
			trigger=Trigger.objects.get(id=request.POST['trigger']),
			email=email,
			defaults={
				"extra": {
					"desired_outcome": request.POST['desired_outcome'],
					"campaign": get_sanitized_campaign(request),
				}
			})

	return HttpResponse(str(ret), content_type="text/plain")


@require_http_methods(['POST'])
@json_response
def submit(request):
	# In order to return something in an error condition, we
	# have to wrap the transaction *inside* a try/except and
	# form the response based on the exception.
	try:
		return create_pledge(request)
	except HumanReadableValidationError as e:
		return { "status": "error", "message": str(e) }

def get_sanitized_campaign(request):
	campaign = request.POST['campaign']
	if campaign is not None:
		if campaign.strip().lower() in ("", "none"):
			campaign = None
	return campaign

@transaction.atomic
def update_pledge_profiles(pledges, new_profile):
	# The user is updating their ContributorInfo profile. Set
	# the profile of any open pledges to the new instance. Delete
	# any ContributorInfo objects no longer needed.

	# Lock.
	pledges = pledges.select_for_update()

	# Sanity check that we do not update a pledge that is not open.
	if pledges.exclude(status=PledgeStatus.Open).exists():
		raise ValueError('pledges should be a QuerySet of only open pledges')

	# Get existing ContributorInfos on those pledges.
	prev_profiles = set(p.profile for p in pledges)

	# Update pledges to new profile.
	pledges.update(profile=new_profile)

	# Delete any of the previous ContributorInfos that are no longer needed.
	for ci in prev_profiles:
		if not ci.pledges.exists():
			ci.delete()

@transaction.atomic
def create_pledge(request):
	p = Pledge()

	# trigger
	p.trigger = Trigger.objects.get(id=request.POST['trigger'])
	p.made_after_trigger_execution = (p.trigger.status == TriggerStatus.Executed)

	# campaign
	p.campaign = get_sanitized_campaign(request)

	# Set user from logged in state.
	if request.user.is_authenticated():
		# This is an authentiated user.
		p.user = request.user
		exists_filters = { 'user': p.user }

	# Anonymous user is submitting a pledge with an email address & password.
	elif request.POST.get("hasPassword") == "1":
		from itfsite.accounts import User
		from itfsite.betteruser import LoginException
		try:
			user = User.authenticate(request.POST['email'].strip(), request.POST['password'].strip())
			# Login succeeded.
			p.user = user
			exists_filters = { 'user': p.user }
		except LoginException as e:
			# Login failed. We did client-side validation so this should
			# not occur. Treat as if the user didn't provide a password.
			pass

	# Anonymous user and/or authentication failed.
	# Will do email verification below.
	if not p.user:
		p.email = request.POST.get('email').strip()
		from itfsite.betteruser import validate_email, ValidateEmailResult
		if validate_email(p.email, simple=True) != ValidateEmailResult.Valid:
			raise Exception("email is out of range")
		exists_filters = { 'email': p.email }

	# If the user has already made this pledge, it is probably a
	# synchronization problem. Just redirect to that pledge.
	p_exist = Pledge.objects.filter(trigger=p.trigger, **exists_filters).first()
	if p_exist is not None:
		return { "status": "ok" }

	# Field values & validation.

	# integer fields that have the same field name as form element name
	for field in ('algorithm', 'desired_outcome'):
		try:
			setattr(p, field, int(request.POST[field]))
		except ValueError:
			raise Exception("%s is out of range" % field)

	# float fields that have the same field name as form element name
	for field in ('amount', 'incumb_challgr'):
		try:
			setattr(p, field, float(request.POST[field]))
		except ValueError:
			raise Exception("%s is out of range" % field)

	# normalize the filter_party field
	if request.POST['filter_party'] in ('DR', 'RD'):
		p.filter_party = None # no filter
	elif request.POST['filter_party'] == 'D':
		p.filter_party = ActorParty.Democratic
	elif request.POST['filter_party'] == 'R':
		p.filter_party = ActorParty.Republican

	# Validation. Some are checked client side, so errors are internal
	# error conditions and not validation problems to show the user.
	if p.algorithm != Pledge.current_algorithm()["id"]:
		raise Exception("algorithm is out of range")
	if not (0 <= p.desired_outcome < len(p.trigger.outcomes)):
		raise Exception("desired_outcome is out of range")
	if not (p.trigger.get_minimum_pledge() <= p.amount <= Pledge.current_algorithm()["max_contrib"]):
		raise Exception("amount is out of range")
	if p.incumb_challgr not in (-1, 0, 1):
		raise Exception("incumb_challgr is out of range")
	if p.filter_party == ActorParty.Independent:
		raise Exception("filter_party is out of range")

	# Get a ContributorInfo to assign to the Pledge.
	if not request.POST["copyFromPledge"]:
		# Create a new ContributorInfo record from the submitted info.
		contribdata = { }

		# string fields that go straight into the extras dict.
		contribdata['contributor'] = { }
		for field in (
			'contribNameFirst', 'contribNameLast',
			'contribAddress', 'contribCity', 'contribState', 'contribZip',
			'contribOccupation', 'contribEmployer'):
			contribdata['contributor'][field] = request.POST[field].strip()
			
		# Validate & store the billing fields.
		#
		# (Including the expiration date so that we can know that a
		# card has expired prior to using the DE token.)
		ccnum = request.POST['billingCCNum'].replace(" ", "").strip() # Stripe's javascript inserts spaces
		ccexpmonth = int(request.POST['billingCCExpMonth'])
		ccexpyear = int(request.POST['billingCCExpYear'])
		cccvc = request.POST['billingCCCVC'].strip()
		contribdata['billing'] = {
			'cc_num': ccnum, # is hashed before going into database
			'cc_exp_month': ccexpmonth,
			'cc_exp_year': ccexpyear,
		}

		# Create a ContributorInfo instance. We need a saved instance
		# so we can assign it to the pledge (the profile field is NOT NULL).
		# It's saved again below.
		ci = ContributorInfo.objects.create()
		ci.set_from(contribdata)

		# Save. We need a Pledge ID to form an authorization test.
		p.profile = ci
		p.save()

		# For logging:
		# Add information from the HTTP request in case we need to
		# block IPs or something.
		aux_data = {
			"httprequest": { k: request.META.get(k) for k in ('REMOTE_ADDR', 'REQUEST_URI', 'HTTP_USER_AGENT') },
		}

		# Perform an authorization test on the credit card and store some CC
		# details in the ContributorInfo object.
		#
		# This may raise all sorts of exceptions, which will cause the database
		# transaction to roll back. A HumanReadableValidationError will be caught
		# in the calling function and shown to the user. Other exceptions will
		# just generate generic unhandled error messages.
		#
		# Note that any exception after this point is okay because the authorization
		# will expire on its own anyway.
		run_authorization_test(p, ccnum, cccvc, aux_data)

		# Re-save the ContributorInfo instance now that it has the CC token.
		ci.save(override_immutable_check=True)

		# If the user has other open pledges, update their profiles to the new
		# ContributorInfo instance --- i.e. update their contributor and payment
		# info.
		update_pledge_profiles(get_user_pledges(p.user, request).filter(status=PledgeStatus.Open), ci)

	else:
		# This is a returning user and we are re-using info from a previous pledge.
		# Validate that the pledge id corresponds to a pledge previously submitted
		# by this user. Only works for an authenticated user.
		if not p.user: raise Exception("Can't have copyFromPledge set and not be an authenticated user.")
		prev_p = Pledge.objects.get(
			id=request.POST["copyFromPledge"],
			user=p.user)
		p.profile = prev_p.profile
		p.save()

	if not p.user:
		# The pledge needs to get confirmation of the user's email address,
		# which will lead to account creation.
		p.send_email_confirmation(first_try=True)

		# And in order for the user to be able to view the pledge on the
		# next page, prior to email confirmation, we'll need to set a token
		# to grant permission. Only hold up to 20 values.
		request.session['anon_pledge_created'] = \
			request.session.get('anon_pledge_created', [])[-20:] \
			+ [p.id]

		# Wipe the IncompletePledge because the user finished the form.
		IncompletePledge.objects.filter(email=p.email, trigger=p.trigger).delete()

	# If the user had good authentication but wasn't logged in yet, log them
	# in now. This messes up the CSRF token but the client should redirect to
	# a new page anyway.
	if p.user and p.user != request.user:
		from django.contrib.auth import login
		login(request, p.user)

	# Client will reload the page.
	return { "status": "ok" }

@json_response
def cancel_pledge(request):
	# Get the pledge. Check authorization.
	p = Pledge.objects.get(id=request.POST['pledge'])
	if not (p.user == request.user or p.id in request.session.get('anon_pledge_created', [])):
		raise Exception()
	p.delete()
	return { "status": "ok" }

@anonymous_view
@json_response
def trigger_execution_report(request, id):
	# get the object & validate that there is data
	trigger = get_object_or_404(Trigger, id=id)
	try:
		te = trigger.execution
	except TriggerExecution.DoesNotExist:
		raise Http404("This trigger is not executed.")
	if te.pledge_count_with_contribs == 0:
		raise Http404("This trigger did not have any contributions.")
	if te.pledge_count != trigger.pledge_count:
		raise Http404("This trigger is still being executed.")

	# form response
	ret = { }

	# Aggregates by outcome.
	ret['outcomes'] = te.get_outcomes()

	# Aggregates by actor.
	actions = list(te.actions.all().select_related('actor'))
	actions.sort(key = lambda a : ((a.total_contributions_for + a.total_contributions_against) == 0, -(a.total_contributions_for - a.total_contributions_against), a.actor.name_sort))
	def build_actor_info(action):
		ret = {
			"name": action.name_long,
			"action": action.outcome_label(),
			"contribs": action.total_contributions_for,
			"contribs_to_opponent": action.total_contributions_against,
			"actor_id": action.actor.id,
		}
		for idscheme in ('bioguide', 'govtrack', 'opensecrets'):
			if idscheme in action.extra['legislators-current']['id']:
				ret[idscheme+"_id"] = action.extra['legislators-current']['id'][idscheme]
		for key in ('state', 'district', 'url', 'end'):
			v = action.extra['legislators-current']['term'].get(key)
			if key == 'url': key = 'homepage'
			if key == 'end': key = 'term_end'
			if v:
				ret[key] = v
		return ret
	ret['actors'] = [build_actor_info(a) for a in actions]

	# All donors.
	from contrib.models import PledgeExecutionProblem, Contribution
	ret['donors'] = [{
		"desired_outcome": pe.pledge.desired_outcome_label,
		"contribs": pe.charged-pe.fees,
		"congressional_district": pe.district,
		"date": pe.pledge.created,
	} for pe in te.pledges.filter(problem=PledgeExecutionProblem.NoProblem).select_related('pledge', 'pledge__trigger')]

	# All contributions.
	ret['contributions'] = [{
		'amount': c.amount,
		'donor_congressional_district': c.pledge_execution.district,
		'donor_desired_outcome': c.pledge_execution.pledge.desired_outcome_label,
		'recipient_name': c.recipient.name,
		'recipient_actor_id' if not c.recipient.is_challenger else "incumbent_actor_id":
			c.recipient.actor_id,
	} for c in Contribution.objects.filter(pledge_execution__pledge__trigger=trigger)
		.select_related('pledge_execution', 'pledge_execution__pledge', 'pledge_execution__pledge_trigger', 'recipient')]

	# report
	return ret
