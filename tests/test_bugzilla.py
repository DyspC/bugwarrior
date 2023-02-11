import datetime
from unittest import mock
from collections import namedtuple

from bugwarrior.services.bz import BugzillaService

from .base import ConfigTest, ServiceTest, AbstractServiceTest


class FakeBugzillaLib:
    def __init__(self, records):
        self.records = records

    def query(self, query):
        return [namedtuple('Record', list(record.keys()))(**record)
                for record in self.records]


class TestBugzillaServiceConfig(ConfigTest):

    def setUp(self):
        super().setUp()
        self.config = {
            'general': {'targets': ['mybz']},
            'mybz': {'service': 'bugzilla'},
        }

    def test_validate_config_username_password(self):
        self.config['mybz'].update({
            'base_uri': 'https://one.com/',
            'username': 'me',
            'password': 'mypas',
        })

        # no error expected
        self.validate()

    def test_validate_config_api_key(self):
        self.config['mybz'].update({
            'base_uri': 'https://one.com/',
            'username': 'me',
            'api_key': '123',
        })

        # no error expected
        self.validate()

    def test_validate_config_api_key_no_username(self):
        self.config['mybz'].update({
            'base_uri': 'https://one.com/',
            'api_key': '123',
        })

        self.assertValidationError(
            '[mybz]\nusername  <- field required')

    def test_validate_legacy_schemeless_uri(self):
        self.config['mybz'].update({
            'base_uri': 'one.com/',
            'username': 'me',
            'password': 'mypas',
        })

        # no error expected
        self.validate()


class TestBugzillaService(AbstractServiceTest, ServiceTest):
    SERVICE_CONFIG = {
        'service': 'bugzilla',
        'base_uri': 'https://one.com/',
        'username': 'hello',
        'password': 'there',
    }

    arbitrary_record = {
        'product': 'Product',
        'component': 'Something',
        'priority': 'urgent',
        'status': 'NEW',
        'summary': 'This is the issue summary',
        'id': 1234567,
        'flags': [],
        'assigned_to': None,
    }

    arbitrary_datetime = datetime.datetime.now(tz=datetime.timezone.utc)

    def setUp(self):
        super().setUp()
        with mock.patch('bugzilla.Bugzilla'):
            self.service = self.get_mock_service(BugzillaService)

    def get_mock_service(self, *args, **kwargs):
        service = super().get_mock_service(
            *args, **kwargs)
        service.bz = FakeBugzillaLib([self.arbitrary_record])
        service._get_assigned_date = (
            lambda issues: self.arbitrary_datetime.isoformat())
        return service

    def test_api_key_supplied(self):
        with mock.patch('bugzilla.Bugzilla'):
            self.service = self.get_mock_service(
                BugzillaService,
                config_overrides={
                    'base_uri': 'https://one.com/',
                    'username': 'me',
                    'api_key': '123',
                })

    def test_to_taskwarrior(self):
        arbitrary_extra = {
            'url': 'http://path/to/issue/',
            'annotations': [
                'Two',
            ],
        }

        issue = self.service.get_issue_for_record(
            self.arbitrary_record,
            arbitrary_extra,
        )

        expected_output = {
            'project': self.arbitrary_record['component'],
            'priority': issue.PRIORITY_MAP[self.arbitrary_record['priority']],
            'annotations': arbitrary_extra['annotations'],

            issue.STATUS: self.arbitrary_record['status'],
            issue.URL: arbitrary_extra['url'],
            issue.SUMMARY: self.arbitrary_record['summary'],
            issue.BUG_ID: self.arbitrary_record['id'],
            issue.PRODUCT: self.arbitrary_record['product'],
            issue.COMPONENT: self.arbitrary_record['component'],
        }
        actual_output = issue.to_taskwarrior()

        self.assertEqual(actual_output, expected_output)

    def test_issues(self):
        issue = next(self.service.issues())

        expected = {
            'annotations': [],
            'bugzillabugid': 1234567,
            'bugzillastatus': 'NEW',
            'bugzillasummary': 'This is the issue summary',
            'bugzillaurl': 'https://one.com/show_bug.cgi?id=1234567',
            'bugzillaproduct': 'Product',
            'bugzillacomponent': 'Something',
            'description': ('(bw)Is#1234567 - This is the issue summary .. '
                            'https://one.com/show_bug.cgi?id=1234567'),
            'priority': 'H',
            'project': 'Something',
            'tags': []}

        self.assertEqual(issue.get_taskwarrior_record(), expected)

    def test_only_if_assigned(self):
        with mock.patch('bugzilla.Bugzilla'):
            self.service = self.get_mock_service(
                BugzillaService,
                config_overrides={
                    'only_if_assigned': 'hello',
                })

        assigned_records = [
            {
                'product': 'Product',
                'component': 'Something',
                'priority': 'urgent',
                'status': 'ASSIGNED',
                'summary': 'This is the issue summary',
                'id': 1234568,
                'flags': [],
                'assigned_to': 'hello'
            },
            {
                'product': 'Product',
                'component': 'Something',
                'priority': 'urgent',
                'status': 'ASSIGNED',
                'summary': 'This is the issue summary',
                'id': 1234569,
                'flags': [],
                'assigned_to': 'somebodyelse'
            },
        ]
        self.service.bz.records.extend(assigned_records)

        issues = self.service.issues()

        expected = {
            'annotations': [],
            'bugzillaassignedon': self.arbitrary_datetime,
            'bugzillabugid': 1234568,
            'bugzillastatus': 'ASSIGNED',
            'bugzillasummary': 'This is the issue summary',
            'bugzillaurl': 'https://one.com/show_bug.cgi?id=1234568',
            'bugzillaproduct': 'Product',
            'bugzillacomponent': 'Something',
            'description': ('(bw)Is#1234568 - This is the issue summary .. '
                            'https://one.com/show_bug.cgi?id=1234568'),
            'priority': 'H',
            'project': 'Something',
            'tags': []}

        self.assertEqual(next(issues).get_taskwarrior_record(), expected)

        # Only one issue is assigned.
        self.assertRaises(StopIteration, lambda: next(issues))

    def test_also_unassigned(self):
        with mock.patch('bugzilla.Bugzilla'):
            self.service = self.get_mock_service(
                BugzillaService,
                config_overrides={
                    'only_if_assigned': 'hello',
                    'also_unassigned': True,
                })

        assigned_records = [
            {
                'product': 'Product',
                'component': 'Something',
                'priority': 'urgent',
                'status': 'ASSIGNED',
                'summary': 'This is the issue summary',
                'id': 1234568,
                'flags': [],
                'assigned_to': 'hello'
            },
            {
                'product': 'Product',
                'component': 'Something',
                'priority': 'urgent',
                'status': 'ASSIGNED',
                'summary': 'This is the issue summary',
                'id': 1234569,
                'flags': [],
                'assigned_to': 'somebodyelse'
            },
        ]
        self.service.bz.records.extend(assigned_records)

        issues = self.service.issues()

        self.assertIn(next(issues).get_taskwarrior_record()['bugzillabugid'],
                      [1234567, 1234568])
        self.assertIn(next(issues).get_taskwarrior_record()['bugzillabugid'],
                      [1234567, 1234568])
        # Only two issues are assigned to the user or unassigned.
        self.assertRaises(StopIteration, lambda: next(issues))
