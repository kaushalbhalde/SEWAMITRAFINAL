import os
import tempfile
import unittest

import app as app_module


class WorkerProfilePhotoTests(unittest.TestCase):
    def setUp(self):
        fd, temp_db = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        app_module.DB_PATH = temp_db
        app_module.init_db()

    def tearDown(self):
        try:
            conn = app_module.get_db()
            conn.close()
        except Exception:
            pass
        try:
            if os.path.exists(app_module.DB_PATH):
                os.remove(app_module.DB_PATH)
        except PermissionError:
            pass

    def test_worker_profile_supports_previous_work_photos(self):
        conn = app_module.get_db()
        info = conn.execute('PRAGMA table_info(worker_profiles)').fetchall()
        columns = [row[1] for row in info]
        self.assertIn('previous_work_photos', columns)

        with app_module.app.test_client() as client:
            conn = app_module.get_db()
            user = conn.execute("SELECT id FROM users WHERE email = 'worker1@bridge.local'").fetchone()
            conn.close()
            with client.session_transaction() as sess:
                sess['user_id'] = user['id']

            resp = client.put('/api/profile', json={
                'name': 'Arjun Electrician',
                'phone': '9876500002',
                'address': 'Ulsoor, Bengaluru',
                'bio': 'Updated bio',
                'skills': 'Electrical,Repair/Maintenance',
                'hourly_rate': 500,
                'daily_rate': 3000,
                'portfolio': 'Past electrical jobs',
                'previous_work_photos': ['/static/uploads/work/1.jpg', '/static/uploads/work/2.jpg']
            })
            self.assertEqual(resp.status_code, 200)

            profile_resp = client.get(f"/api/profile/{user['id']}")
            self.assertEqual(profile_resp.status_code, 200)
            payload = profile_resp.get_json()
            self.assertEqual(payload['worker_profile']['previous_work_photos'], ['/static/uploads/work/1.jpg', '/static/uploads/work/2.jpg'])

    def test_public_profile_view_does_not_require_login(self):
        with app_module.app.test_client() as client:
            user = client.application.config.get('TEST_USER_ID')
            if user is None:
                conn = app_module.get_db()
                user = conn.execute("SELECT id FROM users WHERE email = 'worker1@bridge.local'").fetchone()['id']
                conn.close()
            resp = client.get(f'/api/profile/{user}')
            self.assertEqual(resp.status_code, 200)

    def test_demo_kaushal_worker_profile_is_seeded(self):
        conn = app_module.get_db()
        user = conn.execute("SELECT * FROM users WHERE email = 'kaushal@bridge.local'").fetchone()
        self.assertIsNotNone(user)
        self.assertEqual(user['role'], 'worker')
        self.assertEqual(user['name'], 'Kaushal')
        profile = conn.execute("SELECT * FROM worker_profiles WHERE user_id = ?", (user['id'],)).fetchone()
        self.assertIsNotNone(profile)
        self.assertIn('Cooking', profile['skills'])
        self.assertIn('/static/uploads/previous-work/kaushal-cooking-sample.svg', profile['previous_work_photos'])
        conn.close()

    def test_customer_can_send_price_offer_to_available_worker(self):
        conn = app_module.get_db()
        customer = conn.execute("SELECT id FROM users WHERE email = 'customer@bridge.local'").fetchone()
        worker = conn.execute("SELECT id FROM users WHERE email = 'worker2@bridge.local'").fetchone()
        job = conn.execute(
            "SELECT id FROM jobs WHERE customer_id = ? AND status = 'open' LIMIT 1",
            (customer['id'],)
        ).fetchone()
        conn.close()

        with app_module.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user_id'] = customer['id']
            response = client.post(f"/api/jobs/{job['id']}/invite-worker", json={
                'worker_id': worker['id'],
                'proposed_price': 1800,
                'price_type': 'total',
                'message': 'Can you take this job for this amount?'
            })
            self.assertEqual(response.status_code, 201)

        conn = app_module.get_db()
        application = conn.execute(
            'SELECT * FROM job_applications WHERE job_id = ? AND worker_id = ?',
            (job['id'], worker['id'])
        ).fetchone()
        negotiation = conn.execute(
            'SELECT * FROM negotiations WHERE application_id = ?',
            (application['id'],)
        ).fetchone()
        self.assertEqual(application['proposed_price'], 1800)
        self.assertEqual(negotiation['proposed_by'], 'customer')
        conn.close()

    def test_customer_profile_template_hides_quick_details(self):
        template_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'profile.html')
        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()

        self.assertIn("u.role === 'worker' ? `", template)
        self.assertIn('Quick Details', template)

    def test_marketplace_has_multiple_distinct_demo_products(self):
        conn = app_module.get_db()
        products = conn.execute('SELECT name FROM products ORDER BY name').fetchall()
        names = [row['name'] for row in products]
        self.assertGreater(len(names), 5)
        self.assertIn('LED Emergency Light', names)
        self.assertIn('Smart Water Filter', names)
        conn.close()

    def test_cooperative_gigs_page_exists(self):
        with app_module.app.test_client() as client:
            resp = client.get('/cooperative.html')
            self.assertEqual(resp.status_code, 200)
            html = resp.get_data(as_text=True)
            self.assertIn('Cooperative Gigs', html)
            self.assertIn('Community Projects', html)
            self.assertIn('Join a Project', html)
            self.assertIn('Donate Now', html)

    def test_notifications_api_exposes_unread_count_and_mark_read(self):
        with app_module.app.test_client() as client:
            conn = app_module.get_db()
            user = conn.execute("SELECT id FROM users WHERE email = 'customer@bridge.local'").fetchone()
            conn.execute(
                'INSERT INTO notifications (user_id, title, message, type, read_flag) VALUES (?,?,?,?,0)',
                (user['id'], 'Test notification', 'Your job has been updated.', 'info')
            )
            conn.commit()
            conn.close()

            with client.session_transaction() as sess:
                sess['user_id'] = user['id']

            resp = client.get('/api/notifications')
            self.assertEqual(resp.status_code, 200)
            payload = resp.get_json()
            self.assertIn('items', payload)
            self.assertIn('unread_count', payload)
            self.assertGreaterEqual(payload['unread_count'], 1)

            notification_id = payload['items'][0]['id']
            mark_resp = client.post(f'/api/notifications/{notification_id}/read')
            self.assertEqual(mark_resp.status_code, 200)

            updated = client.get('/api/notifications')
            updated_payload = updated.get_json()
            item = next(n for n in updated_payload['items'] if n['id'] == notification_id)
            self.assertEqual(item['read_flag'], 1)


if __name__ == '__main__':
    unittest.main()
