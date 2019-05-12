import six
import requests
import json

from bugwarrior.config import die, asbool
from bugwarrior.services import Issue, IssueService, ServiceClient

import logging
log = logging.getLogger(__name__)

class OpenProjectClient(ServiceClient):
    def __init__(self, url, key):
        self.url = url
        self.key = key

    def find_issues(self, issue_limit=100, only_if_assigned=True):
        args = {}

        if issue_limit is not None:
            args["pageSize"] = issue_limit

        if only_if_assigned:
            args["filters"] = json.dumps([{"assignee": {"operator": "=", "values": ["me"]}}])

        return self.call_api("/api/v3/work_packages", args)["_embedded"]["elements"]

    def call_api(self, uri, params):
        url = self.url.rstrip("/") + uri
        kwargs = { 'params': params }


        if self.key:
            kwargs['auth'] = ('apikey', self.key)

        return self.json_response(requests.get(url, **kwargs))

class OpenProjectIssue(Issue):
    URL = 'openprojecturl'
    SUBJECT = 'openprojectsubject'
    ID = 'openprojectid'
    DESCRIPTION = 'openprojectdescription'

    UDAS = {
        URL: {
            'type': 'string',
            'label': 'OpenProject work package URL'
        },
        SUBJECT: {
            'type': 'string',
            'label': 'OpenProject Subject'
        },
        ID: {
            'type': 'numeric',
            'lable': 'OpenProject ID'
        },
        DESCRIPTION: {
            'type': 'string',
            'label': 'OpenProject Description'
        }
    }
    UNIQUE_KEY = (ID, )

    PRIORITY_MAP = {
        'Low': 'L',
        'Normal': 'M',
        'High': 'H',
        'Immediate': 'H'
    }

    def to_taskwarrior(self):
        due_date = self.record.get('dueDate')
        start_date = self.record.get('startDate')
        updated_on = self.record.get('updatedAt')
        created_on = self.record.get('createdAt')
        assigned_to = self.record.get('assignee')

        if due_date:
            due_date = self.parse_date(due_date).replace(microsecond=0)
        if start_date:
            start_date = self.parse_date(start_date).replace(microsecond=0)
        if updated_on:
            updated_on = self.parse_date(updated_on).replace(microsecond=0)
        if created_on:
            created_on = self.parse_date(created_on).replace(microsecond=0)

        return {
            'project': self.get_project_name(),
            'priority': self.get_priority(),
            self.URL: self.get_issue_url(),
            self.SUBJECT: self.record['subject'],
            self.ID: self.record['id'],
            self.DESCRIPTION: self.get_description(),
        }

    def get_project_name(self):
        self.record['_links']['project']['title']
    def get_priority(self):
        self.PRIORITY_MAP.get(
            self.record['_links'].get('priority', {}).get('Name'),
            self.origin['default_priority']
        )
    def get_issue_url(self):
        return (
            self.origin['url'] + "/work_packages/" + six.text_type(self.record["id"])
        )
    def get_description(self):
        self.record['description']['raw']

    def get_default_description(self):
        return self.build_default_description(
            title=self.record['subject'],
            url=self.get_processed_url(self.get_issue_url()),
            number=self.record['id'],
            cls='issue',
        )


class OpenProjectService(IssueService):
    ISSUE_CLASS = OpenProjectIssue
    CONFIG_PREFIX = 'openproject'

    def __init__(self, *args, **kw):
        super(OpenProjectService, self).__init__(*args, **kw)

        self.url = self.config.get('url').rstrip('/')
        self.key = self.get_password('key')
        self.issue_limit = self.config.get('issue_limit')

        self.client = OpenProjectClient(self.url, self.key)

        self.project_name = self.config.get('project_name')

    def get_service_metadata(self):
        return {
            'project_name': self.project_name,
            'url': self.url
        }

    @staticmethod
    def get_keyring_service(service_config):
        url = service_config.get('url')
        login = service_config.get('login')
        return "openproject://%s@%s/" % (login, url)

    @classmethod
    def validate_config(cls, service_config, target):
        for k in ('url', 'key'):
            if k not in service_config:
                die('[%s] has no "openproject.%s"' % (target, k))

        IssueService.validate_config(service_config, target)

    def issues(self):
        only_if_assigned = self.config.get('only_if_assigned', True)
        issues = self.client.find_issues(self.issue_limit, only_if_assigned)
        log.debug(" Found %i total.", len(issues))
        for issue in issues:
            yield self.get_issue_for_record(issue)
