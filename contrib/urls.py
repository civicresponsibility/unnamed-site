from django.conf.urls import patterns, include, url

urlpatterns = patterns('',
	url(r'a/(?P<id>\d+)(?:/[a-z0-9_-]+)?$', 'contrib.views.trigger', name='trigger'),
	url(r'a/(?P<id>\d+)-(?P<trigger_customization_id>\d+)(?:/[a-z0-9_-]+/[a-z0-9_-]+)?$', 'contrib.views.trigger', name='trigger'),
	url(r'contrib/_submit$', 'contrib.views.submit', name='contrib_submit'),
	url(r'contrib/_defaults$', 'contrib.views.get_user_defaults', name='contrib_defaults'),
	url(r'contrib/_cancel$', 'contrib.views.cancel_pledge', name='cancel_pledge'),
	url(r'contrib/_validate_email$', 'contrib.views.validate_email'),
	url(r'totals$', 'contrib.views.report', name='report'),
)
