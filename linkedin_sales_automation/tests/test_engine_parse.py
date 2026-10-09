from odoo.tests import BaseCase, tagged

from ..models.li_engine_parse import (
    connect_outcome, connected_usernames, error_kind, inbox_preview, inbox_threads, message_outcome,
    parse_search_results, parse_thread, people_search_url,
)

THREAD = """Today
Taha Sohail sent the following message at 10:05 AM
View Taha Sohail’s profile
Taha Sohail
Taha Sohail  10:05 AM
Hi Ali, thanks for connecting!
Ali Raza sent the following messages at 10:20 AM
View Ali Raza’s profile
Ali Raza
Ali Raza  10:20 AM
Thanks Taha.
What do you do exactly?
Seen by Ali Raza at 10:21 AM.
"""

SEARCH = {
    'url': 'https://www.linkedin.com/search/results/people/?keywords=founder',
    'sections': {'search_results': 'Ali Raza\n• 2nd\nFounder at Brand X\nLahore, Pakistan\nConnect\n'
                                   'Sara Khan\nView Sara Khan’s profile\n• 3rd+\nCEO, Shopify brand\nKarachi\n'
                                   '12 mutual connections\nMessage\n'},
    'references': {'search_results': [
        {'kind': 'person', 'url': '/in/ali-raza/', 'text': 'Ali Raza'},
        {'kind': 'company', 'url': '/company/brand-x/', 'text': 'Brand X'},
        {'kind': 'person', 'url': '/in/sara-khan-123/', 'text': 'Sara Khan'},
        {'kind': 'person', 'url': '/in/taha-test/', 'text': 'Taha Sohail'},
    ]},
}


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestEngineParse(BaseCase):

    def test_thread_with_group_lines(self):
        messages = parse_thread(THREAD, 'Taha Sohail', 'Ali Raza')
        self.assertEqual(messages, [
            {'sender_name': 'Taha Sohail', 'text': 'Hi Ali, thanks for connecting!'},
            {'sender_name': 'Ali Raza', 'text': 'Thanks Taha.'},
            {'sender_name': 'Ali Raza', 'text': 'What do you do exactly?'},
        ])

    def test_thread_without_group_lines(self):
        text = 'Taha Sohail  9:00 AM\nHello Ali\nAli Raza  9:30 AM\nHi!\nYESTERDAY\nAli Raza\nAre you there?'
        self.assertEqual(parse_thread(text, 'Taha Sohail', 'Ali Raza'), [
            {'sender_name': 'Taha Sohail', 'text': 'Hello Ali'},
            {'sender_name': 'Ali Raza', 'text': 'Hi!'},
            {'sender_name': 'Ali Raza', 'text': 'Are you there?'},
        ])

    def test_thread_ignores_linkedin_interface_text(self):
        # the online-status banner and the message box are not messages written by hand
        text = ('Taha Sohail sent the following message at 10:51 PM\nTaha Sohail  10:51 PM\n'
                'Hi Ali, thanks for connecting!\n'
                'Your online status is visible. You can change this in your settings. Manage\nDismiss\n'
                'Write a message…\nPress Enter to Send\nSend')
        self.assertEqual(parse_thread(text, 'Taha Sohail', 'Ali Raza'),
                         [{'sender_name': 'Taha Sohail', 'text': 'Hi Ali, thanks for connecting!'}])

    def test_thread_ignores_quick_reply_suggestions(self):
        # LinkedIn suggests answers to the account owner below the last message
        text = ('Taha Sohail sent the following message at 10:12 PM\nTaha Sohail\nHi Ali, thanks for connecting!\n'
                'Ali Raza sent the following message at 10:40 PM\nAli Raza\nThanks, Taha\n'
                'Reply to conversation with "Thanks Ali"\nThanks Ali\n'
                'Reply to conversation with “OK”\nOK\n'
                'Reply to conversation with "You are welc…"\nYou are welcome')
        self.assertEqual(parse_thread(text, 'Taha Sohail', 'Ali Raza'), [
            {'sender_name': 'Taha Sohail', 'text': 'Hi Ali, thanks for connecting!'},
            {'sender_name': 'Ali Raza', 'text': 'Thanks, Taha'},
        ])
        # a real reply that only looks like one keeps its place
        real = ('Ali Raza sent the following message at 10:40 PM\nAli Raza\nOK\nDismiss the idea, we use Odoo')
        self.assertEqual([m['text'] for m in parse_thread(real, 'Taha Sohail', 'Ali Raza')],
                         ['OK', 'Dismiss the idea, we use Odoo'])

    def test_thread_unreadable_and_empty(self):
        self.assertIsNone(parse_thread('Some page text without any sender', 'Taha Sohail', 'Ali Raza'))
        self.assertIsNone(parse_thread('', 'Taha Sohail', 'Ali Raza'))

    def test_link_preview_lines_are_marked(self):
        text = ('Taha Sohail sent the following message at 4:00 PM\nTaha Sohail\n'
                'Book a call: https://calendly.com/taha/30min\nCalendly - Taha Sohail\ncalendly.com\n'
                'Ali Raza sent the following message at 4:10 PM\nAli Raza\nBooked!')
        messages = parse_thread(text, 'Taha Sohail', 'Ali Raza')
        self.assertEqual([m.get('after_link', False) for m in messages], [False, True, True, False])
        self.assertEqual(messages[-1], {'sender_name': 'Ali Raza', 'text': 'Booked!'})

    def test_search_results(self):
        people = parse_search_results(SEARCH, own_username='taha-test')
        self.assertEqual([(p['username'], p['name'], p['headline'], p['location']) for p in people], [
            ('ali-raza', 'Ali Raza', 'Founder at Brand X', 'Lahore, Pakistan'),
            ('sara-khan-123', 'Sara Khan', 'CEO, Shopify brand', 'Karachi'),
        ])
        self.assertEqual(people[0]['linkedin_url'], 'https://www.linkedin.com/in/ali-raza/')
        self.assertEqual(connected_usernames(SEARCH), {'ali-raza', 'sara-khan-123', 'taha-test'})
        self.assertEqual(parse_search_results({}), [])
        self.assertIn('network=%5B%22F%22%5D', people_search_url('Ali Raza', ['F']))

    def test_inbox(self):
        data = {'sections': {'inbox': 'Ali Raza\nOct 7\nYou: Hi Ali, thanks for connecting!\nSara Khan\n4:10 PM\nHello'},
                'references': {'inbox': [{'kind': 'conversation', 'url': '/messaging/thread/2-abc==/',
                                          'text': 'Ali Raza'},
                                         {'kind': 'person', 'url': '/in/x/', 'text': 'X'}]}}
        self.assertEqual(inbox_threads(data), {'ali raza': '2-abc=='})
        first = inbox_preview(data, 'Ali Raza')
        self.assertTrue(first)
        self.assertEqual(inbox_preview(data, 'Nobody Here'), '')
        data['sections']['inbox'] = data['sections']['inbox'].replace('You: Hi Ali', 'Ali: Sounds good')
        self.assertNotEqual(inbox_preview(data, 'Ali Raza'), first)

    def test_send_outcomes(self):
        self.assertEqual(connect_outcome({'status': 'connected'})[0], 'sent')
        self.assertEqual(connect_outcome({'status': 'pending'})[0], 'pending')
        self.assertEqual(connect_outcome({'status': 'already_connected'})[0], 'already_connected')
        self.assertEqual(connect_outcome({'status': 'accepted'})[0], 'already_connected')
        self.assertEqual(connect_outcome({'status': 'custom_note_limit_reached'})[0], 'custom_note_limit_reached')
        self.assertEqual(connect_outcome({'status': 'follow_only'})[0], 'not_invitable')
        self.assertEqual(connect_outcome({'status': 'outcome_unknown'})[:2], ('unknown', False))
        self.assertEqual(connect_outcome({'status': 'send_failed', 'message': "You've reached the weekly "
                                          "invitation limit"})[0], 'weekly_invite_limit')
        self.assertEqual(message_outcome({'status': 'sent', 'sent': True, 'retry_safe': False})[0], 'sent')
        self.assertEqual(message_outcome({'status': 'send_failed', 'sent': False, 'retry_safe': False})[:2],
                         ('unknown', False))
        self.assertEqual(message_outcome({'status': 'recipient_not_found', 'sent': False, 'retry_safe': True})[:2],
                         ('failed', True))
        self.assertEqual(message_outcome({'status': 'enter_to_send_enabled', 'retry_safe': True})[0], 'enter_to_send')

    def test_engine_without_session_counts_as_session_error(self):
        # the real engine 4.26.2 without a session answers this instead of failing
        text = ('A LinkedIn login window is open and login is still in progress. This is not a failure. Complete '
                'the sign-in in the browser, then call this exact tool again in about 30 seconds to resume.')
        self.assertEqual(error_kind(text)[0], 'session')
        self.assertEqual(error_kind('The shared LinkedIn browser has no usable session, and it cannot sign in by '
                                    'itself. Retry this tool: the client will open a login window.')[0], 'session')

    def test_error_kinds(self):
        self.assertEqual(error_kind('Session expired. Run with --login to create a new browser profile.')[0],
                         'session')
        self.assertEqual(error_kind('LinkedIn has restricted access to this account and asks for identity '
                                    'verification. ... run --login.')[0], 'restricted')
        self.assertEqual(error_kind('Rate limit detected. Wait 600 seconds before trying again.'), ('rate_limit', 600))
        self.assertEqual(error_kind('Profile not found. Check the profile URL is correct.')[0], 'not_found')
        self.assertEqual(error_kind('Connection failed after 1 attempts: Read timed out.')[0], 'timeout')
        self.assertEqual(error_kind('Element not found. LinkedIn page structure may have changed.')[0], 'other')


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestEngineEncoding(BaseCase):
    """Engine answers are UTF-8 even as a charset-less text/event-stream."""

    def test_event_stream_is_decoded_as_utf8(self):
        import json
        from unittest.mock import patch
        import requests
        from ..models.li_mcp_client import McpClient
        body = 'event: message\ndata: %s\n\n' % json.dumps(
            {'jsonrpc': '2.0', 'id': 1, 'result': {'content': [{'type': 'text', 'text': 'Zoë • 3rd+ لاہور'}]}},
            ensure_ascii=False)
        response = requests.models.Response()
        response.status_code = 200
        response._content = body.encode('utf-8')
        response.headers['Content-Type'] = 'text/event-stream'
        response.encoding = 'ISO-8859-1'               # what requests picks for text/* without charset
        with patch('requests.post', return_value=response):
            result = McpClient('http://127.0.0.1:1/mcp', retries=1).request('tools/call', {})
        self.assertEqual(result['content'][0]['text'], 'Zoë • 3rd+ لاہور')

    def test_repair_mojibake(self):
        from ..models.li_engine_parse import repair_mojibake
        garbled = 'Zoë • 3rd+ لاہور'.encode('utf-8').decode('latin-1')
        self.assertEqual(repair_mojibake(garbled), 'Zoë • 3rd+ لاہور')
        for fine in ('Zoë Müller', 'Café • Lahore', 'Plain text', '', None):
            self.assertEqual(repair_mojibake(fine), fine)
        self.assertEqual(parse_search_results({
            'sections': {'search_results': 'Hafiz Awan\n· 3rd+\nCEO at Odoo\nLahore'},
            'references': {'search_results': [{'kind': 'person', 'url': '/in/hafiz/', 'text': 'Hafiz Awan'}]},
        })[0]['headline'], 'CEO at Odoo')
