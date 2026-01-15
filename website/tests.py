from django.test import TestCase, Client
from django.urls import reverse
from website.models import NewsItem, ContactMessage, Category

class NewsItemModelTests(TestCase):
    def test_slug_auto_generation_and_uniqueness(self):
        item1 = NewsItem.objects.create(title='Mon Titre', type='post', status='published')
        item2 = NewsItem.objects.create(title='Mon Titre', type='post', status='published')
        self.assertNotEqual(item1.slug, '')
        self.assertNotEqual(item2.slug, '')
        self.assertNotEqual(item1.slug, item2.slug)

    def test_event_date_cleared_for_non_event(self):
        item = NewsItem.objects.create(title='Article', type='post', status='draft', date_event=None)
        self.assertIsNone(item.date_event)

class HomeViewTests(TestCase):
    def setUp(self):
        for i in range(5):
            NewsItem.objects.create(title=f'Post {i}', type='post', status='published')
        for i in range(4):
            NewsItem.objects.create(title=f'Event {i}', type='event', status='published')

    def test_home_page_status_and_context(self):
        client = Client()
        resp = client.get(reverse('website:home'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('posts', resp.context)
        self.assertIn('events', resp.context)
        self.assertLessEqual(len(resp.context['posts']), 3)
        self.assertLessEqual(len(resp.context['events']), 3)

class ContactFormTests(TestCase):
    def test_contact_form_submission(self):
        client = Client()
        data = {
            'name': 'Alice',
            'email': 'alice@example.com',
            'phone': '+22900000000',
            'subject': 'Sujet test',
            'request_type': 'info',
            'message': 'Bonjour ceci est un message.'
        }
        resp = client.post(reverse('website:contact'), data, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(ContactMessage.objects.filter(email='alice@example.com').exists())
        # Vérifie qu'un message de succès est présent
        messages = list(resp.context['messages'])
        self.assertTrue(any('succès' in m.message.lower() for m in messages))

__all__ = [
    'NewsItemModelTests',
    'HomeViewTests',
    'ContactFormTests',
]
