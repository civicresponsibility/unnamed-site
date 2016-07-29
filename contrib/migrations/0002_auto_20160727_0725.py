# -*- coding: utf-8 -*-
# Generated by Django 1.9.7 on 2016-07-27 11:25
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('itfsite', '0001_initial'),
        ('contrib', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='triggercustomization',
            name='owner',
            field=models.ForeignKey(help_text='The user/organization which created the TriggerCustomization.', on_delete=django.db.models.deletion.CASCADE, related_name='triggers', to='itfsite.Organization'),
        ),
        migrations.AddField(
            model_name='triggercustomization',
            name='trigger',
            field=models.ForeignKey(help_text='The Trigger that this TriggerCustomization customizes.', on_delete=django.db.models.deletion.CASCADE, related_name='customizations', to='contrib.Trigger'),
        ),
        migrations.AddField(
            model_name='trigger',
            name='owner',
            field=models.ForeignKey(blank=True, help_text='The user/organization which created the trigger and can update it. Empty for Triggers created by us.', null=True, on_delete=django.db.models.deletion.PROTECT, to='itfsite.Organization'),
        ),
        migrations.AddField(
            model_name='trigger',
            name='trigger_type',
            field=models.ForeignKey(help_text='The type of the trigger, which determines how it is described in text.', on_delete=django.db.models.deletion.PROTECT, to='contrib.TriggerType'),
        ),
        migrations.AddField(
            model_name='tip',
            name='profile',
            field=models.ForeignKey(help_text='The contributor information (name, address, etc.) and billing information used for this Tip.', on_delete=django.db.models.deletion.PROTECT, related_name='tips', to='contrib.ContributorInfo'),
        ),
        migrations.AddField(
            model_name='tip',
            name='recipient',
            field=models.ForeignKey(help_text='The recipient of the tip.', on_delete=django.db.models.deletion.PROTECT, to='itfsite.Organization'),
        ),
        migrations.AddField(
            model_name='tip',
            name='user',
            field=models.ForeignKey(blank=True, help_text='The user making the Tip.', null=True, on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='tip',
            name='via_campaign',
            field=models.ForeignKey(blank=True, help_text='The Campaign that this Tip was made via.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='tips', to='itfsite.Campaign'),
        ),
        migrations.AddField(
            model_name='tip',
            name='via_pledge',
            field=models.OneToOneField(blank=True, help_text='The executed Pledge that this Tip was made via.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='tip', to='contrib.Pledge'),
        ),
        migrations.AddField(
            model_name='recipient',
            name='actor',
            field=models.OneToOneField(blank=True, help_text='The Actor that this recipient corresponds to (i.e. this Recipient is an incumbent).', null=True, on_delete=django.db.models.deletion.CASCADE, to='contrib.Actor'),
        ),
        migrations.AddField(
            model_name='pledgeexecution',
            name='pledge',
            field=models.OneToOneField(help_text='The Pledge this execution information is about.', on_delete=django.db.models.deletion.PROTECT, related_name='execution', to='contrib.Pledge'),
        ),
        migrations.AddField(
            model_name='pledgeexecution',
            name='trigger_execution',
            field=models.ForeignKey(help_text='The TriggerExecution this execution information is about.', on_delete=django.db.models.deletion.PROTECT, related_name='pledges', to='contrib.TriggerExecution'),
        ),
        migrations.AddField(
            model_name='pledge',
            name='anon_user',
            field=models.ForeignKey(blank=True, help_text='When an anonymous user makes a pledge, a one-off object is stored here and we send a confirmation email.', null=True, on_delete=django.db.models.deletion.CASCADE, to='itfsite.AnonymousUser'),
        ),
        migrations.AddField(
            model_name='pledge',
            name='profile',
            field=models.ForeignKey(help_text='The contributor information (name, address, etc.) and billing information used for this Pledge. Immutable and cannot be changed after execution.', on_delete=django.db.models.deletion.PROTECT, related_name='pledges', to='contrib.ContributorInfo'),
        ),
        migrations.AddField(
            model_name='pledge',
            name='trigger',
            field=models.ForeignKey(help_text='The Trigger that this Pledge is for.', on_delete=django.db.models.deletion.PROTECT, related_name='pledges', to='contrib.Trigger'),
        ),
        migrations.AddField(
            model_name='pledge',
            name='user',
            field=models.ForeignKey(blank=True, help_text="The user making the pledge. When an anonymous user makes a pledge, this is null, the user's email address is stored in an AnonymousUser object referenced in anon_user, and the pledge should be considered unconfirmed/provisional and will not be executed.", null=True, on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='pledge',
            name='via_campaign',
            field=models.ForeignKey(blank=True, help_text='The Campaign that this Pledge was made via.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='pledges', to='itfsite.Campaign'),
        ),
        migrations.AddField(
            model_name='incompletepledge',
            name='completed_pledge',
            field=models.ForeignKey(blank=True, help_text='If the user came back and finished a Pledge, that pledge.', null=True, on_delete=django.db.models.deletion.CASCADE, to='contrib.Pledge'),
        ),
        migrations.AddField(
            model_name='incompletepledge',
            name='trigger',
            field=models.ForeignKey(help_text='The Trigger that the pledge was for.', on_delete=django.db.models.deletion.CASCADE, to='contrib.Trigger'),
        ),
        migrations.AddField(
            model_name='incompletepledge',
            name='via_campaign',
            field=models.ForeignKey(blank=True, help_text='The Campaign that this Pledge was made via.', null=True, on_delete=django.db.models.deletion.CASCADE, to='itfsite.Campaign'),
        ),
        migrations.AddField(
            model_name='contribution',
            name='action',
            field=models.ForeignKey(help_text='The Action this contribution was made in reaction to.', on_delete=django.db.models.deletion.PROTECT, to='contrib.Action'),
        ),
        migrations.AddField(
            model_name='contribution',
            name='pledge_execution',
            field=models.ForeignKey(help_text='The PledgeExecution this execution information is about.', on_delete=django.db.models.deletion.PROTECT, related_name='contributions', to='contrib.PledgeExecution'),
        ),
        migrations.AddField(
            model_name='contribution',
            name='recipient',
            field=models.ForeignKey(help_text='The Recipient this contribution was sent to.', on_delete=django.db.models.deletion.PROTECT, related_name='contributions', to='contrib.Recipient'),
        ),
        migrations.AddField(
            model_name='cancelledpledge',
            name='anon_user',
            field=models.ForeignKey(blank=True, help_text='When an anonymous user makes a pledge, a one-off object is stored here and we send a confirmation email.', null=True, on_delete=django.db.models.deletion.CASCADE, to='itfsite.AnonymousUser'),
        ),
        migrations.AddField(
            model_name='cancelledpledge',
            name='trigger',
            field=models.ForeignKey(help_text='The Trigger that the pledge was for.', on_delete=django.db.models.deletion.CASCADE, to='contrib.Trigger'),
        ),
        migrations.AddField(
            model_name='cancelledpledge',
            name='user',
            field=models.ForeignKey(blank=True, help_text='The user who made the pledge, if not anonymous.', null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='cancelledpledge',
            name='via_campaign',
            field=models.ForeignKey(blank=True, help_text='The Campaign that this Pledge was made via.', null=True, on_delete=django.db.models.deletion.CASCADE, to='itfsite.Campaign'),
        ),
        migrations.AddField(
            model_name='actor',
            name='challenger',
            field=models.OneToOneField(blank=True, help_text="The *current* Recipient that contributions to this Actor's challenger go to. Independents don't have challengers because they have no opposing party.", null=True, on_delete=django.db.models.deletion.CASCADE, related_name='challenger_to', to='contrib.Recipient'),
        ),
        migrations.AddField(
            model_name='action',
            name='actor',
            field=models.ForeignKey(help_text='The Actor who took this action.', on_delete=django.db.models.deletion.PROTECT, to='contrib.Actor'),
        ),
        migrations.AddField(
            model_name='action',
            name='challenger',
            field=models.ForeignKey(blank=True, help_text="The Recipient that contributions to this Actor's challenger go to, at the time of the Action. Independents don't have challengers because they have no opposing party.", null=True, on_delete=django.db.models.deletion.CASCADE, to='contrib.Recipient'),
        ),
        migrations.AddField(
            model_name='action',
            name='execution',
            field=models.ForeignKey(help_text='The TriggerExecution that created this object.', on_delete=django.db.models.deletion.CASCADE, related_name='actions', to='contrib.TriggerExecution'),
        ),
        migrations.AlterUniqueTogether(
            name='triggercustomization',
            unique_together=set([('trigger', 'owner')]),
        ),
        migrations.AlterUniqueTogether(
            name='recipient',
            unique_together=set([('office_sought', 'party')]),
        ),
        migrations.AlterUniqueTogether(
            name='pledge',
            unique_together=set([('trigger', 'user'), ('trigger', 'anon_user')]),
        ),
        migrations.AlterIndexTogether(
            name='pledge',
            index_together=set([('trigger', 'via_campaign')]),
        ),
        migrations.AlterUniqueTogether(
            name='contribution',
            unique_together=set([('pledge_execution', 'action')]),
        ),
        migrations.AlterUniqueTogether(
            name='action',
            unique_together=set([('execution', 'actor')]),
        ),
    ]