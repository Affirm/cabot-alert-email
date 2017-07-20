from os import environ as env

from django.conf import settings
from django.core.mail import EmailMessage
from django.template import Context, Template
from urlparse import urljoin

from cabot.cabotapp.alert import AlertPlugin

import requests
import logging


logger = logging.getLogger(__name__)


email_template = """Service {{ service.name }} {{ scheme }}://{{ host }}{% url 'service' pk=service.id %} {% if service.overall_status != service.PASSING_STATUS %}alerting with status: {{ service.overall_status }}{% else %}is back to normal{% endif %}.
{% if service.overall_status != service.PASSING_STATUS %}
{% if panel_urls %}Grafana links for the failing checks:{{ panel_urls }}.{% endif %}
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
        """
        Get a PNG image of a Grafana panel.
        :param panel_url: URL for the panel
        :param grafana_instance: GrafanaInstance object
        :return: the image content or None
        """
        panel_url = panel_url.replace(urljoin(grafana_instance.url, '/'), '')
        rendered_image_url = urljoin('render/', panel_url)
        # Unfortunately this works for the normal image but not render
        rendered_image_url = rendered_image_url.replace('$__all', 'All')

        try:
            image_request = grafana_instance.get_request(rendered_image_url)
            image_request.raise_for_status()
            return image_request.content
        except requests.exceptions.RequestException as e:
            logger.error('Failed to get Grafana panel image for email alert')
            return None

    def send_alert(self, service, users, duty_officers):
        """
        Send an email to the specified users with the service status and (possibly) Grafana panel images/links.
        """
        emails = [u.email for u in users if u.email] + [u.email for u in duty_officers if u.email]
        if not emails:
            return

        panel_urls = []
        images = {}
        if service.overall_status != service.PASSING_STATUS:
            subject = '%s status for service: %s' % (
                service.overall_status, service.name)

            failing_metrics_checks = service.status_checks \
                .exclude(calculated_status=service.PASSING_STATUS) \
                .exclude(metricsstatuscheckbase__isnull=True) \
                .filter(active=True)

            for check in failing_metrics_checks:
                if check.grafana_panel is not None:
                    panel_urls.append(check.grafana_panel.panel_url)
                    image = self._get_grafana_panel_image(check.grafana_panel.panel_url,
                                                          check.grafana_panel.grafana_instance)
                    if image is not None:
                        images[check.name] = image

        else:
            subject = 'Service back to normal: %s' % (service.name,)

        c = Context({
            'service': service,
            'host': settings.WWW_HTTP_HOST,
            'scheme': settings.WWW_SCHEME,
            'panel_urls': '\n'.join(panel_urls)
        })

        t = Template(email_template)

        message = EmailMessage(
            subject=subject,
            body=t.render(c),
            from_email='Cabot <%s>' % env.get('CABOT_FROM_EMAIL'),
            to=emails,
        )
        logger.critical(str(type(message)))
        logger.critical(message)

        for name, image in images.iteritems():
            logger.critical('attaching something {} {}'.format(name, image))
            message.attach('{}.png'.format(name), image, 'image/png')

        message.send()
