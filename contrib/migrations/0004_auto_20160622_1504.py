# -*- coding: utf-8 -*-
# Generated by Django 1.9.7 on 2016-06-22 19:04
from __future__ import unicode_literals

from django.db import migrations
import itfsite.utils


class Migration(migrations.Migration):

    dependencies = [
        ('contrib', '0003_contribution_recipient_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='trigger',
            name='outcomes',
            field=itfsite.utils.JSONField(default='[{"vote_key": "+", "label": "Yes on This Vote", "object": "in favor of the bill"}, {"vote_key": "-", "label": "No on This Vote", "object": "against passage of the bill"}]', help_text="An array (order matters!) of information for each possible outcome of the trigger, e.g. ['Voted Yes', 'Voted No']."),
        ),
        migrations.AlterUniqueTogether(
            name='contribution',
            unique_together=set([('pledge_execution', 'action')]),
        ),
    ]