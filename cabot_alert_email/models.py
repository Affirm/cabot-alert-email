from os import environ as env

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.urlresolvers import reverse
from django.template import Context, Template
from urlparse import urljoin

from cabot.cabotapp.alert import AlertPlugin
from cabot.cabotapp.models.service import CALCULATED_FAILING_STATUS

import requests
import logging

email_template = """Service {{ service.name }} {{ scheme }}://{{ host }}{% url 'service' pk=service.id %} {% if service.overall_status != service.PASSING_STATUS %}alerting with status: {{ service.overall_status }}{% else %}is back to normal{% endif %}.
{% if service.overall_status != service.PASSING_STATUS %}
CHECKS FAILING:{% for check in service.all_failing_checks %}
  FAILING - {{ check.name }} - Type: {{ check.check_category }} - Importance: {{ check.get_importance_display }}{% endfor %}
{% if service.all_passing_checks %}
Passing checks:{% for check in service.all_passing_checks %}
  PASSING - {{ check.name }} - Type: {{ check.check_category }} - Importance: {{ check.get_importance_display }}{% endfor %}
{% endif %}
{% endif %}
"""

class EmailAlert(AlertPlugin):
    name = "Email"
    author = "Jonathan Balls"

    def _get_grafana_panel_image(self, panel_url, grafana_instance):
        panel_url = panel_url.replace(grafana_instance.url, '')
        rendered_image_url = urljoin('render/', panel_url)

        image_request = grafana_instance.get_request(rendered_image_url)
        try:
            image_request.raise_for_status()
            return image_request.content
        except requests.exceptions.HTTPError:
            return None

    def send_alert(self, service, users, duty_officers):
        emails = [u.email for u in users if u.email] + [u.email for u in duty_officers if u.email]
        if not emails:
            return
        c = Context({
            'service': service,
            'host': settings.WWW_HTTP_HOST,
            'scheme': settings.WWW_SCHEME
        })
        if service.overall_status != service.PASSING_STATUS:
            subject = '%s status for service: %s' % (
                service.overall_status, service.name)
        else:
            subject = 'Service back to normal: %s' % (service.name,)
        t = Template(email_template)

        message = EmailMessage(
            subject=subject,
            message=t.render(c),
            from_email='Cabot <%s>' % env.get('CABOT_FROM_EMAIL'),
            recipient_list=emails,
        )

        failing_metrics_checks = service.status_checks.filter(calculated_status=CALCULATED_FAILING_STATUS)\
            .exclude(metricsstatuscheckbase__isnull=True)\
            .filter(active=True)

        for check in failing_metrics_checks:
            if check.grafana_panel is not None:
                message.attach('grafana.png',
                               self._get_grafana_panel_image(check.grafana_panel.panel_url,
                                                             check.grafana_panel.grafana_instance),
                               'image/png')

        message.send()