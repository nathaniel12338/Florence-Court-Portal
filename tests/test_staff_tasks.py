import io
import os
import re
import tempfile
import unittest
from datetime import date, datetime, time
from decimal import Decimal
from unittest.mock import patch

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import (
    CourseCatalog,
    CourseResultApproval,
    FeeInvoice,
    FeeSchedule,
    CourseGrade,
    Jss1,
    Jss2,
    LibraryResource,
    PasswordResetChallenge,
    ResultApproval,
    Staff,
    StaffTask,
    admitted,
    app,
    bcrypt,
    db,
    ensure_database_exists,
    hash_password,
    migrate_result_approvals,
    portal,
    result_grade_for_total,
    send_email,
    student_class_invoices,
)


class StaffTaskFlowTests(unittest.TestCase):
    def setUp(self):
        app.config.update(
            TESTING=True,
            SECRET_KEY='test-secret',
            MAIL_SERVER='',
            MAIL_PORT=587,
            MAIL_USERNAME='',
            MAIL_PASSWORD='',
            MAIL_SENDER='',
            MAIL_USE_TLS=True,
            MAIL_USE_SSL=False,
        )
        self.email_sender = patch('app.send_email', return_value=True)
        self.email_mock = self.email_sender.start()
        self.addCleanup(self.email_sender.stop)
        with app.app_context():
            db.drop_all()
            db.create_all()

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def create_admitted_student(self, first_name, email, admission_id, entry_class):
        student = admitted(
            username=first_name.lower(),
            email=email,
            firstName=first_name,
            lastName='Student',
            dob='2015-01-01',
            gender='F',
            birth_certificate='certificate.pdf',
            payment_evidence='receipt.pdf',
            state_origin='Lagos',
            entry_class=entry_class,
            entry_session='2026/2027',
            recent_result='result.pdf',
            phone_number='08000000000',
            address='School Road',
            admission_id=admission_id,
            guardian_name='Parent Name',
        )
        db.session.add(student)
        return student

    def test_admin_creates_staff_assigns_task_and_staff_updates_status(self):
        admin = app.test_client()
        response = admin.post(
            '/schoolAdmin',
            data={'admin_id': '2025', 'password': 'victor1'},
        )
        self.assertEqual(response.status_code, 302)

        response = admin.post(
            '/staff-management',
            data={
                'staff_id': 'STAFF-01',
                'full_name': 'Ada Teacher',
                'email': 'ada@example.com',
                'password': 'teacher-pass-1',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.email_mock.assert_called_once()
        self.assertEqual(self.email_mock.call_args.args[0], 'ada@example.com')
        self.assertIn('Temporary password', self.email_mock.call_args.args[2])

        with app.app_context():
            staff = Staff.query.filter_by(staff_id='STAFF-01').one()
            staff_pk = staff.id

        response = admin.get('/table1')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Ada Teacher', response.data)

        response = admin.post(
            '/table1',
            data={
                'classe': 'jss1',
                'term': 'first',
                'subject[]': ['Science'],
                'techername[]': ['Ada Teacher'],
                'date[]': ['2026-10-15'],
                'time[]': ['09:30'],
            },
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            lesson = Jss1.query.one()
            self.assertEqual(lesson.date.isoformat(), '2026-10-15')
            self.assertEqual(lesson.time.strftime('%H:%M'), '09:30')

        response = admin.post(
            '/tasks',
            data={
                'title': 'Prepare lesson',
                'description': 'Prepare the science lesson plan.',
                'staff_id': str(staff_pk),
                'due_date': '2026-10-15',
            },
        )
        self.assertEqual(response.status_code, 302)

        staff_client = app.test_client()
        response = staff_client.post(
            '/schoolAdmin',
            data={'admin_id': 'STAFF-01', 'password': 'teacher-pass-1'},
        )
        self.assertEqual(response.status_code, 302)
        response = staff_client.get('/tasks')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Prepare lesson', response.data)

        with app.app_context():
            task_id = StaffTask.query.one().id

        response = staff_client.post(
            f'/tasks/{task_id}/status',
            data={'status': 'completed'},
        )
        self.assertEqual(response.status_code, 302)

        with app.app_context():
            self.assertEqual(StaffTask.query.one().status, 'completed')

        response = admin.get('/tasks')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Ada Teacher', response.data)
        self.assertIn(b'Completed', response.data)

    def test_admin_can_edit_staff_details_and_change_assigned_course_teacher(self):
        admin = app.test_client()
        admin.post(
            '/schoolAdmin',
            data={'admin_id': '2025', 'password': 'victor1'},
        )
        with app.app_context():
            ada = Staff(
                staff_id='STAFF-EDIT-01',
                full_name='Ada Teacher',
                email='ada.edit@example.com',
                password_hash=hash_password('teacher-pass-1'),
            )
            ben = Staff(
                staff_id='STAFF-EDIT-02',
                full_name='Ben Teacher',
                email='ben.edit@example.com',
                password_hash=hash_password('teacher-pass-2'),
            )
            db.session.add_all((ada, ben, CourseCatalog(name='Mathematics')))
            db.session.flush()
            lesson = Jss1(
                classe='JSS 1',
                term='first',
                subject='Mathematics',
                techername=ada.full_name,
                date=date(2026, 10, 15),
                time=time(9, 30),
            )
            db.session.add(lesson)
            db.session.commit()
            ada_id, ben_id, lesson_id = ada.id, ben.id, lesson.id

        response = admin.get('/staff-management')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Mathematics', response.data)
        self.assertIn(b'Edit details &amp; courses', response.data)

        response = admin.post(
            '/staff-management',
            data={
                'action': 'update_staff',
                'staff_pk': str(ada_id),
                'staff_id': 'STAFF-EDIT-NEW',
                'full_name': 'Ada Updated',
                'email': 'ada.updated@example.com',
                'is_active': 'enabled',
                'password': '',
            },
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            updated_ada = db.session.get(Staff, ada_id)
            self.assertEqual(updated_ada.staff_id, 'STAFF-EDIT-NEW')
            self.assertEqual(updated_ada.full_name, 'Ada Updated')
            self.assertEqual(updated_ada.email, 'ada.updated@example.com')
            self.assertEqual(db.session.get(Jss1, lesson_id).techername, 'Ada Updated')

        response = admin.get(f'/admin/courses?teacher_id={ada_id}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Current courses for Ada Updated', response.data)
        self.assertIn(b'Mathematics', response.data)

        response = admin.post(
            '/staff-management',
            data={
                'action': 'change_assignment',
                'staff_pk': str(ada_id),
                'class_key': 'jss1',
                'lesson_id': str(lesson_id),
                'target_staff_id': str(ben_id),
            },
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertEqual(db.session.get(Jss1, lesson_id).techername, 'Ben Teacher')

    def test_admin_result_readiness_refreshes_and_is_scoped_to_selected_class(self):
        admin = app.test_client()
        admin.post(
            '/schoolAdmin',
            data={'admin_id': '2025', 'password': 'victor1'},
        )
        with app.app_context():
            ada = self.create_admitted_student(
                'Ada', 'ada.jss1-results@example.com', '51001', 'JSS 1'
            )
            ben = self.create_admitted_student(
                'Ben', 'ben.jss1-results@example.com', '51002', 'JSS 1'
            )
            cy = self.create_admitted_student(
                'Cy', 'cy.jss2-results@example.com', '51003', 'JSS 2'
            )
            teacher = Staff(
                staff_id='STAFF-CLASS-RESULTS',
                full_name='Results Teacher',
                email='results.teacher@example.com',
                password_hash=hash_password('teacher-pass-1'),
            )
            db.session.add(teacher)
            db.session.flush()
            db.session.add_all((
                Jss1(
                    classe='JSS 1', term='first', subject='Science',
                    techername=teacher.full_name, date=date(2026, 10, 15),
                    time=time(9, 30),
                ),
                Jss2(
                    classe='JSS 2', term='first', subject='Science',
                    techername=teacher.full_name, date=date(2026, 10, 15),
                    time=time(10, 30),
                ),
                CourseGrade(
                    student_id=ada.id, staff_id=teacher.id,
                    timetable_class='jss1', class_name='JSS 1',
                    term='first', subject='Science', ca1_score=20,
                    exam_score=30, grade='Fail',
                ),
                CourseGrade(
                    student_id=cy.id, staff_id=teacher.id,
                    timetable_class='jss2', class_name='JSS 2',
                    term='first', subject='Science', ca1_score=20,
                    exam_score=30, grade='Fail',
                ),
                CourseGrade(
                    student_id=cy.id, staff_id=teacher.id,
                    timetable_class='jss1', class_name='JSS 1',
                    term='first', subject='Science', ca1_score=20,
                    exam_score=30, grade='Fail',
                ),
            ))
            db.session.commit()
            ben_id, teacher_id = ben.id, teacher.id

        response = admin.get('/datatable?class=jss1')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'JSS 1', response.data)
        self.assertNotIn(b'<h2>JSS 2', response.data)
        self.assertIn(b'1 incomplete', response.data)
        self.assertNotIn(b'Ready for approval', response.data)
        self.assertEqual(response.headers.get('Cache-Control', '').split(',')[0], 'no-store')

        with app.app_context():
            db.session.add(CourseGrade(
                student_id=ben_id,
                staff_id=teacher_id,
                timetable_class='jss1',
                class_name='JSS 1',
                term='first',
                subject='Science',
                ca1_score=20,
                exam_score=30,
                grade='Fail',
            ))
            db.session.commit()

        response = admin.get('/datatable?class=jss1')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Ready for approval', response.data)
        self.assertIn(b'2 of 2 student marks complete', response.data)
        self.assertNotIn(b'<h2>JSS 2', response.data)

        response = admin.get('/datatable')
        self.assertIn(b'JSS 1', response.data)
        self.assertIn(b'JSS 2', response.data)

    def test_staff_can_only_update_own_tasks(self):
        with app.app_context():
            staff = Staff(
                staff_id='STAFF-01',
                full_name='Ada Teacher',
                email='ada@example.com',
                password_hash=hash_password('teacher-pass-1'),
            )
            other_staff = Staff(
                staff_id='STAFF-02',
                full_name='Sam Teacher',
                email='sam@example.com',
                password_hash=hash_password('teacher-pass-2'),
            )
            db.session.add_all([staff, other_staff])
            db.session.flush()
            task = StaffTask(
                staff_id=other_staff.id,
                title='Private assignment',
                description='Only the assigned staff member can change this.',
            )
            db.session.add(task)
            db.session.commit()
            task_id = task.id

        client = app.test_client()
        client.post(
            '/schoolAdmin',
            data={'admin_id': 'STAFF-01', 'password': 'teacher-pass-1'},
        )
        response = client.post(
            f'/tasks/{task_id}/status',
            data={'status': 'completed'},
        )
        self.assertEqual(response.status_code, 404)

        with app.app_context():
            self.assertEqual(StaffTask.query.one().status, 'pending')

    def test_mysql_database_is_created_using_quoted_identifier(self):
        with patch('app.create_engine') as create_engine:
            connection = create_engine.return_value.connect.return_value.__enter__.return_value
            connection.dialect.identifier_preparer.quote.return_value = '`school_db`'

            ensure_database_exists('mysql://test:test@localhost/school_db')

            connection.exec_driver_sql.assert_called_once_with(
                'CREATE DATABASE IF NOT EXISTS `school_db`'
            )
            create_engine.return_value.dispose.assert_called_once_with()

    def test_admission_form_has_state_and_gender_dropdowns(self):
        response = app.test_client().get('/apply')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<select id="state_origin" name="state_origin" required>', response.data)
        self.assertIn(b'<option value="Federal Capital Territory">', response.data)
        self.assertIn(b'<select id="gender" name="gender" required>', response.data)
        self.assertIn(b'<option value="M">Male</option>', response.data)
        self.assertNotIn(b'type="radio" name="gender"', response.data)
        self.assertIn(b'<select id="entry_session" name="entry_session" required>', response.data)
        current_session = f'{date.today().year}/{date.today().year + 1}'
        self.assertIn(f'<option value="{current_session}"'.encode(), response.data)
        self.assertNotIn(b'name="entry_session" type="text"', response.data)
        self.assertNotIn(b'name="payment_evidence"', response.data)

    def test_admission_form_rejects_invalid_state_or_gender(self):
        response = app.test_client().post(
            '/apply',
            data={
                'username': 'student',
                'firstName': 'Ada',
                'lastName': 'Teacher',
                'email': 'ada@example.com',
                'dob': '2015-01-01',
                'state_origin': 'Not a Nigerian state',
                'gender': 'X',
                'entry_class': 'Basic 1',
                'entry_session': '2026/2027',
                'phone_number': '08000000000',
                'address': 'School Road',
                'admission_id': '1 2 3 4',
                'guardian_name': 'Parent Name',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Select a valid state of origin and gender.', response.data)

    def test_admission_form_rejects_unlisted_session_and_keeps_dropdown(self):
        response = app.test_client().post(
            '/apply',
            data={
                'username': 'student',
                'firstName': 'Ada',
                'lastName': 'Teacher',
                'email': 'ada@example.com',
                'dob': '2015-01-01',
                'state_origin': 'Lagos',
                'gender': 'F',
                'entry_class': 'Basic 1',
                'entry_session': '2099/2100',
                'phone_number': '08000000000',
                'address': 'School Road',
                'admission_id': '12345',
                'guardian_name': 'Parent Name',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Select a valid school session.', response.data)
        self.assertIn(b'<option value="" disabled selected>Select school session</option>', response.data)
        self.assertNotIn(b'<option value="2099/2100"', response.data)

    def test_admission_reference_is_five_numeric_digits(self):
        response = app.test_client().get('/apply')

        self.assertEqual(response.status_code, 200)
        match = re.search(
            rb'id="admission_id"[^>]*value="([^"]+)"', response.data
        )
        self.assertIsNotNone(match)
        self.assertRegex(match.group(1), rb'^[0-9]{5}$')
        self.assertIn(b'5-digit application reference', response.data)
        self.assertIn(b'id="copy-reference"', response.data)
        self.assertIn(b'Copy application reference', response.data)
        self.assertIn(b'navigator.clipboard.writeText(referenceInput.value)', response.data)

    def test_admin_screens_render_with_admin_navigation(self):
        client = app.test_client()
        client.post(
            '/schoolAdmin',
            data={'admin_id': '2025', 'password': 'victor1'},
        )

        health_response = client.get('/healthz')
        self.assertEqual(health_response.status_code, 200)
        self.assertEqual(health_response.json, {'status': 'ok'})

        for path, heading in (
            ('/Adminpage', b'Good day, Admin'),
            ('/Adminlist', b'Admission applications'),
            ('/students', b'Student directory'),
            ('/table1', b'Timetable &amp; class assignments'),
            ('/admin/courses', b'Courses &amp; teacher assignments'),
            ('/datatable', b'Course results'),
            ('/fees', b'Student fees and invoices'),
            ('/staff-management', b'Staff accounts'),
            ('/tasks', b'Staff tasks'),
        ):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(heading, response.data)
                self.assertIn(b'admin.css', response.data)

    def test_admin_screens_require_admin_login(self):
        client = app.test_client()

        for path in (
            '/Adminpage',
            '/Adminlist',
            '/students',
            '/table1',
            '/admin/courses',
            '/datatable',
            '/fees',
            '/staff-management',
        ):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn('/schoolAdmin', response.headers['Location'])

    def test_admin_login_screen_renders(self):
        response = app.test_client().get('/schoolAdmin')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Welcome back', response.data)
        self.assertIn(b'name="admin_id"', response.data)

    def test_accepted_applicant_is_not_listed_for_review_again(self):
        with app.app_context():
            self.create_admitted_student(
                'Ada', 'ada.accepted@example.com', '30001', 'JSS 1'
            )
            db.session.add(portal(
                username='ben.pending',
                email='ben.pending@example.com',
                firstName='Ben',
                lastName='Pending',
                dob='2015-01-01',
                gender='M',
                birth_certificate='birth.jpg',
                payment_evidence='payment.jpg',
                state_origin='Lagos',
                entry_class='JSS 1',
                entry_session='2026/2027',
                recent_result='result.jpg',
                phone_number='08000000000',
                address='School Road',
                admission_id='30002',
                guardian_name='Parent',
            ))
            db.session.add(portal(
                username='ada.accepted',
                email='ada.accepted@example.com',
                firstName='Ada',
                lastName='Accepted',
                dob='2015-01-01',
                gender='F',
                birth_certificate='birth.jpg',
                payment_evidence='payment.jpg',
                state_origin='Lagos',
                entry_class='JSS 1',
                entry_session='2026/2027',
                recent_result='result.jpg',
                phone_number='08000000000',
                address='School Road',
                admission_id='30001',
                guardian_name='Parent',
            ))
            db.session.commit()

        admin_client = app.test_client()
        admin_client.post(
            '/schoolAdmin',
            data={'admin_id': '2025', 'password': 'victor1'},
        )
        response = admin_client.get('/Adminlist')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Ben Pending', response.data)
        self.assertNotIn(b'Ada Accepted', response.data)

    def test_newly_admitted_student_receives_configured_class_fee_invoices(self):
        with app.app_context():
            self.create_admitted_student(
                'Existing', 'existing.fee-student@example.com', '32001', 'JSS 1'
            )
            db.session.add_all((
                FeeSchedule(
                    class_name='JSS 1',
                    fee_type='Tuition',
                    amount=Decimal('125000.00'),
                ),
                FeeSchedule(
                    class_name='SSS 1',
                    fee_type='Senior tuition',
                    amount=Decimal('175000.00'),
                ),
                portal(
                    username='ben.new-admission',
                    email='ben.new-admission@example.com',
                    firstName='Ben',
                    lastName='New',
                    dob='2015-01-01',
                    gender='M',
                    birth_certificate='birth.pdf',
                    payment_evidence='receipt.pdf',
                    state_origin='Lagos',
                    entry_class='JSS 1',
                    entry_session='2026/2027',
                    recent_result='result.pdf',
                    phone_number='08000000000',
                    address='School Road',
                    admission_id='32002',
                    guardian_name='Parent Name',
                ),
            ))
            db.session.commit()

        admin = app.test_client()
        admin.post(
            '/schoolAdmin',
            data={'admin_id': '2025', 'password': 'victor1'},
        )
        response = admin.post(
            '/Adminlist',
            data={'email': 'ben.new-admission@example.com'},
            headers={'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'fee_warning', response.data)
        with app.app_context():
            invoices = FeeInvoice.query.join(admitted).filter(
                admitted.email == 'ben.new-admission@example.com'
            ).all()
            self.assertEqual(len(invoices), 1)
            self.assertEqual(invoices[0].fee_type, 'Tuition')
            self.assertEqual(invoices[0].class_name, 'JSS 1')
            self.assertEqual(invoices[0].school_session, '2026/2027')

        student = app.test_client()
        student.post(
            '/studentlogin',
            data={
                'email': 'ben.new-admission@example.com',
                'admission_id': '32002',
            },
        )
        response = student.get('/my-invoices')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Tuition', response.data)
        self.assertIn(b'125,000.00', response.data)
        self.assertNotIn(b'Senior tuition', response.data)

    def test_admin_admits_applicant_moves_student_and_teacher_roster_updates(self):
        with app.app_context():
            db.session.add(portal(
                username='ada.applicant',
                email='ada.transfer@example.com',
                firstName='Ada',
                lastName='Applicant',
                dob='2015-01-01',
                gender='F',
                birth_certificate='birth.jpg',
                payment_evidence='payment.jpg',
                state_origin='Lagos',
                entry_class='JSS 1',
                entry_session='2026/2027',
                recent_result='result.jpg',
                phone_number='08000000000',
                address='School Road',
                admission_id='41001',
                guardian_name='Parent Name',
            ))
            teacher = Staff(
                staff_id='STAFF-TRANSFER',
                full_name='Ada Teacher',
                email='teacher.transfer@example.com',
                password_hash=hash_password('teacher-pass-1'),
            )
            db.session.add(teacher)
            db.session.commit()

        admin_client = app.test_client()
        admin_client.post(
            '/schoolAdmin',
            data={'admin_id': '2025', 'password': 'victor1'},
        )
        response = admin_client.get('/Adminlist')
        self.assertIn(b'Ada Applicant', response.data)
        response = admin_client.post(
            '/Adminlist',
            data={'email': 'ada.transfer@example.com'},
            headers={'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'admitted successfully', response.data)
        self.assertIn('41001', self.email_mock.call_args.args[2])
        self.assertIn('Email address:', self.email_mock.call_args.args[2])

        response = admin_client.get('/Adminlist')
        self.assertNotIn(b'Ada Applicant', response.data)
        response = admin_client.get('/students')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'ada.transfer@example.com', response.data)
        self.assertIn(b'41001', response.data)

        with app.app_context():
            student = admitted.query.filter_by(
                email='ada.transfer@example.com'
            ).one()
            teacher = Staff.query.filter_by(staff_id='STAFF-TRANSFER').one()
            student_id = student.id
            teacher_id = teacher.id
            db.session.add(Jss1(
                classe='JSS 1',
                term='first',
                subject='Science',
                techername='Ada Teacher',
                date=date(2026, 10, 15),
                time=time(9, 30),
            ))
            db.session.add(Jss2(
                classe='JSS 2',
                term='first',
                subject='Science',
                techername='Ada Teacher',
                date=date(2026, 10, 15),
                time=time(10, 30),
            ))
            db.session.add(CourseGrade(
                student_id=student_id,
                staff_id=teacher_id,
                timetable_class='jss1',
                class_name='JSS 1',
                term='first',
                subject='Science',
                ca1_score=40,
                exam_score=80,
            ))
            db.session.add(CourseResultApproval(
                timetable_class='jss1',
                class_name='JSS 1',
                term='first',
                subject='Science',
                approved_by='2025',
            ))
            db.session.add(FeeInvoice(
                student_id=student_id,
                fee_type='Tuition',
                class_name='JSS 1',
                school_session='2026/2027',
                amount=125000,
            ))
            db.session.commit()
            invoice_id = FeeInvoice.query.one().id

        response = admin_client.post(
            f'/students/{student_id}/class',
            data={'entry_class': 'JSS 2'},
        )
        self.assertEqual(response.status_code, 302)
        response = admin_client.post(
            f'/students/{student_id}/class',
            data={'entry_class': 'Not a school class'},
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            student = db.session.get(admitted, student_id)
            self.assertEqual(student.entry_class, 'JSS 2')
            invoice = db.session.get(FeeInvoice, invoice_id)
            self.assertEqual(invoice.class_name, 'JSS 1')

        teacher_client = app.test_client()
        teacher_client.post(
            '/schoolAdmin',
            data={'admin_id': 'STAFF-TRANSFER', 'password': 'teacher-pass-1'},
        )
        response = teacher_client.get(
            '/staff/results?class=jss2&term=first&subject=Science'
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Ada Applicant', response.data)

        student_client = app.test_client()
        student_client.post(
            '/studentlogin',
            data={
                'email': 'ada.transfer@example.com',
                'admission_id': '41001',
            },
        )
        response = student_client.get('/student/results')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'JSS 1', response.data)
        self.assertIn(b'Previous class record', response.data)

    def test_admin_can_edit_an_issued_invoice(self):
        with app.app_context():
            student = self.create_admitted_student(
                'Ada', 'ada.invoice-edit@example.com', '41002', 'JSS 1'
            )
            db.session.flush()
            invoice = FeeInvoice(
                student_id=student.id,
                fee_type='Tuition',
                description='Original note',
                class_name='JSS 1',
                school_session='2026/2027',
                amount=125000,
                due_date=date(2026, 11, 1),
            )
            db.session.add(invoice)
            db.session.commit()
            invoice_id = invoice.id

        admin_client = app.test_client()
        admin_client.post(
            '/schoolAdmin',
            data={'admin_id': '2025', 'password': 'victor1'},
        )
        response = admin_client.get('/fees')
        self.assertIn(b'Edit invoice', response.data)
        response = admin_client.post(
            '/fees',
            data={
                'action': 'update_invoice',
                'invoice_id': str(invoice_id),
                'fee_type': 'Examination',
                'amount': '25000',
                'due_date': '2026-12-01',
                'description': 'Updated payment note',
            },
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            invoice = db.session.get(FeeInvoice, invoice_id)
            self.assertEqual(invoice.fee_type, 'Examination')
            self.assertEqual(invoice.amount, Decimal('25000.00'))
            self.assertEqual(invoice.due_date, date(2026, 12, 1))
            self.assertEqual(invoice.description, 'Updated payment note')

    def test_admin_can_email_a_fee_notice_for_an_invoice(self):
        with app.app_context():
            student = self.create_admitted_student(
                'Ada', 'ada.fee-notice@example.com', '41003', 'JSS 1'
            )
            db.session.flush()
            invoice = FeeInvoice(
                student_id=student.id,
                fee_type='Tuition',
                description='Please contact the finance office if you need help.',
                class_name='JSS 1',
                school_session='2026/2027',
                amount=Decimal('125000.00'),
                due_date=date(2026, 11, 1),
            )
            db.session.add(invoice)
            db.session.commit()
            invoice_id = invoice.id

        admin_client = app.test_client()
        admin_client.post(
            '/schoolAdmin',
            data={'admin_id': '2025', 'password': 'victor1'},
        )
        response = admin_client.post(
            '/fees',
            data={'action': 'email_invoice', 'invoice_id': str(invoice_id)},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.email_mock.assert_called_once()
        recipient, subject, message = self.email_mock.call_args.args
        self.assertEqual(recipient, 'ada.fee-notice@example.com')
        self.assertIn('Tuition', subject)
        self.assertIn('NGN 125,000.00', message)
        self.assertIn('Please contact the finance office', message)
        self.assertIn('emailed to ada.fee-notice@example.com', response.get_data(as_text=True))

    def test_admin_can_move_multiple_students_to_a_new_class(self):
        with app.app_context():
            ada = self.create_admitted_student(
                'Ada', 'ada.bulk-move@example.com', '42001', 'JSS 1'
            )
            ben = self.create_admitted_student(
                'Ben', 'ben.bulk-move@example.com', '42002', 'JSS 1'
            )
            cy = self.create_admitted_student(
                'Cy', 'cy.bulk-move@example.com', '42003', 'JSS 2'
            )
            db.session.commit()
            ada_id, ben_id, cy_id = ada.id, ben.id, cy.id

        admin_client = app.test_client()
        admin_client.post(
            '/schoolAdmin',
            data={'admin_id': '2025', 'password': 'victor1'},
        )
        response = admin_client.get('/students')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Admitted student roster', response.data)
        self.assertIn(b'id="bulk-move-form"', response.data)
        self.assertIn(b'class="roster-checkbox"', response.data)
        self.assertIn(b'Change class', response.data)
        response = admin_client.post(
            '/students/move-class',
            data={
                'source_class': 'JSS 1',
                'entry_class': 'JSS 2',
                'student_ids': [str(ada_id), str(ben_id)],
            },
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertEqual(db.session.get(admitted, ada_id).entry_class, 'JSS 2')
            self.assertEqual(db.session.get(admitted, ben_id).entry_class, 'JSS 2')
            self.assertEqual(db.session.get(admitted, cy_id).entry_class, 'JSS 2')

        response = admin_client.post(
            '/students/move-class',
            data={
                'source_class': 'JSS 1',
                'entry_class': 'SSS 1',
                'student_ids': [str(ada_id)],
            },
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertEqual(db.session.get(admitted, ada_id).entry_class, 'JSS 2')

    def test_admin_can_graduate_all_sss3_students_and_keep_read_only_portal_access(self):
        with app.app_context():
            graduating_students = [
                self.create_admitted_student(
                    'Ada', 'ada.graduate@example.com', '43001', 'SSS 3'
                ),
                self.create_admitted_student(
                    'Ben', 'ben.graduate@example.com', '43002', 'SSS 3'
                ),
            ]
            continuing_student = self.create_admitted_student(
                'Cy', 'cy.graduate@example.com', '43003', 'SSS 2'
            )
            db.session.commit()
            graduating_ids = [student.id for student in graduating_students]
            continuing_id = continuing_student.id

        admin_client = app.test_client()
        admin_client.post(
            '/schoolAdmin',
            data={'admin_id': '2025', 'password': 'victor1'},
        )
        roster = admin_client.get('/students')
        self.assertIn(b'Graduate all SSS 3 students', roster.data)
        self.assertIn(b'2 active SSS 3 students ready to graduate', roster.data)

        response = admin_client.post('/students/graduate-sss3')
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertTrue(all(
                db.session.get(admitted, student_id).is_graduated
                for student_id in graduating_ids
            ))
            continuing = db.session.get(admitted, continuing_id)
            self.assertFalse(continuing.is_graduated)
            self.assertEqual(continuing.entry_class, 'SSS 2')

        roster = admin_client.get('/students')
        self.assertIn(b'Graduated', roster.data)
        self.assertIn(b'data-graduated="true"', roster.data)
        for student_id in graduating_ids:
            self.assertNotIn(
                f'action="/students/{student_id}/class"'.encode(),
                roster.data,
            )

        student_client = app.test_client()
        student_client.post(
            '/studentlogin',
            data={
                'email': 'ada.graduate@example.com',
                'admission_id': '43001',
            },
        )
        dashboard = student_client.get('/dashboard')
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(b'Graduated student account', dashboard.data)
        passport = student_client.post(
            '/passport',
            data={},
            follow_redirects=True,
        )
        self.assertEqual(passport.status_code, 200)
        self.assertIn(b'read-only', passport.data)

        blocked_move = admin_client.post(
            f'/students/{graduating_ids[0]}/class',
            data={'entry_class': 'SSS 2'},
        )
        self.assertEqual(blocked_move.status_code, 302)
        with app.app_context():
            self.assertEqual(
                db.session.get(admitted, graduating_ids[0]).entry_class,
                'SSS 3',
            )

    def test_admin_can_assign_one_teacher_and_subject_to_multiple_classes(self):
        with app.app_context():
            db.session.add(Staff(
                staff_id='STAFF-MULTI',
                full_name='Morgan Teacher',
                email='morgan.multi@example.com',
                password_hash=hash_password('teacher-pass-1'),
            ))
            db.session.commit()

        admin_client = app.test_client()
        admin_client.post(
            '/schoolAdmin',
            data={'admin_id': '2025', 'password': 'victor1'},
        )
        response = admin_client.post(
            '/table1',
            data={
                'action': 'assign_multiple_classes',
                'classes[]': ['jss1', 'jss2'],
                'term': 'second',
                'subject': 'Mathematics',
                'teacher': 'Morgan Teacher',
                'date': '2026-11-02',
                'time': '09:30',
            },
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            jss1_lesson = Jss1.query.one()
            jss2_lesson = Jss2.query.one()
            self.assertEqual(jss1_lesson.classe, 'JSS 1')
            self.assertEqual(jss2_lesson.classe, 'JSS 2')
            self.assertEqual(jss1_lesson.subject, 'Mathematics')
            self.assertEqual(jss2_lesson.subject, 'Mathematics')
            self.assertEqual(jss1_lesson.techername, 'Morgan Teacher')
            self.assertEqual(jss2_lesson.techername, 'Morgan Teacher')
            self.assertEqual(jss1_lesson.term, 'second')
            self.assertEqual(jss2_lesson.term, 'second')

        teacher_client = app.test_client()
        teacher_client.post(
            '/schoolAdmin',
            data={'admin_id': 'STAFF-MULTI', 'password': 'teacher-pass-1'},
        )
        response = teacher_client.get('/staff/results')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'JSS 1', response.data)
        self.assertIn(b'JSS 2', response.data)
        self.assertIn(b'Mathematics', response.data)

        response = admin_client.post(
            '/table1',
            data={
                'action': 'assign_multiple_classes',
                'classes[]': ['jss1', 'unknown'],
                'term': 'second',
                'subject': 'Science',
                'teacher': 'Morgan Teacher',
                'date': '2026-11-02',
                'time': '09:30',
            },
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertEqual(Jss1.query.count(), 1)
            self.assertEqual(Jss2.query.count(), 1)

    def test_student_portal_login_dashboard_and_invoice_pages_render(self):
        with app.app_context():
            student = self.create_admitted_student(
                'Ada', 'ada.portal@example.com', '54321', 'JSS 1'
            )
            db.session.flush()
            db.session.add(FeeInvoice(
                student_id=student.id,
                fee_type='Tuition',
                description='First term tuition',
                class_name='JSS 1',
                school_session='2026/2027',
                amount=125000,
                due_date=date(2026, 11, 1),
            ))
            db.session.add(FeeInvoice(
                student_id=student.id,
                fee_type='Other class levy',
                description='Issued to another class',
                class_name='SSS 1',
                school_session='2026/2027',
                amount=5000,
            ))
            db.session.commit()

        anonymous_client = app.test_client()
        response = anonymous_client.get('/studentlogin')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Your school life, all in one place.', response.data)
        self.assertIn(b'name="admission_id"', response.data)

        student_client = app.test_client()
        response = student_client.post(
            '/studentlogin',
            data={'email': 'ada.portal@example.com', 'admission_id': '54321'},
        )
        self.assertEqual(response.status_code, 302)
        response = student_client.get('/dashboard')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Welcome back, Ada!', response.data)
        self.assertIn(b'JSS 1', response.data)
        self.assertIn(b'2026/2027', response.data)
        self.assertIn(b'Tuition', response.data)
        self.assertNotIn(b'Other class levy', response.data)
        self.assertIn(b'125,000.00', response.data)
        self.assertIn(b'Quick links', response.data)
        self.assertIn(b'student_portal.css', response.data)
        self.assertIn(b'id="profile-menu-button"', response.data)
        self.assertIn(b'aria-controls="profile-menu"', response.data)
        self.assertIn(b'class="profile-dropdown"', response.data)
        self.assertIn(b'class="profile-signout" href="/logout"', response.data)
        self.assertIn(b'class="topbar-avatar" src="/static/img/user.jpg"', response.data)
        self.assertNotIn(b'profile-chevron', response.data)
        self.assertIn(b'class="nav-count">1</span>', response.data)
        self.assertNotIn(b'class="sidebar-logout"', response.data)

        response = student_client.get('/my-invoices')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'My invoices', response.data)
        self.assertIn(b'125,000.00', response.data)
        self.assertNotIn(b'Other class levy', response.data)
        self.assertEqual(response.data.count(b'class="student-invoice-card"'), 1)
        self.assertEqual(response.data.count(b'class="student-invoice-entry"'), 1)
        self.assertIn(b'Pay invoice', response.data)
        self.assertIn(b'Online payments are not available yet', response.data)
        self.assertIn(b'payment-dialog', response.data)
        response = student_client.get('/payment')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/my-invoices', response.headers['Location'])
        for path in (
            '/library',
            '/table',
            '/checkresult',
            '/Biodata',
            '/passport',
            '/student/results',
            '/my-invoices',
        ):
            with self.subTest(student_navigation=path):
                response = student_client.get(path)
                self.assertEqual(response.status_code, 200)
                for destination in (
                    '/dashboard',
                    '/my-invoices',
                    '/table',
                    '/student/results',
                    '/checkresult',
                    '/library',
                    '/Biodata',
                    '/passport',
                    '/logout',
                ):
                    self.assertIn(f'href="{destination}"'.encode(), response.data)

    def test_student_timetable_is_class_restricted_and_external_results_form_works(self):
        with app.app_context():
            self.create_admitted_student(
                'Ada', 'ada.navigation@example.com', '54322', 'JSS 1'
            )
            db.session.add(Jss1(
                classe='JSS 1',
                term='first',
                subject='Science',
                techername='Ada Teacher',
                date=date(2026, 10, 15),
                time=time(9, 30),
            ))
            db.session.commit()

        student_client = app.test_client()
        student_client.post(
            '/studentlogin',
            data={'email': 'ada.navigation@example.com', 'admission_id': '54322'},
        )
        response = student_client.get('/table?term=first')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Science', response.data)
        self.assertIn(b'09:30 AM', response.data)

        response = student_client.post(
            '/table',
            data={'classe': 'JSS 2', 'term': 'first'},
        )
        self.assertEqual(response.status_code, 302)
        response = student_client.get(response.headers['Location'])
        self.assertIn(b'only view the timetable for your enrolled class', response.data)

        response = student_client.get('/checkresult')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.count(b'<form'), 1)
        self.assertIn(b'name="registrationnumber"', response.data)
        self.assertIn(b'name="examyear"', response.data)
        response = student_client.post(
            '/checkresult',
            data={'registrationnumber': '', 'examyear': 'not-a-year'},
        )
        self.assertEqual(response.status_code, 302)
        response = student_client.get(response.headers['Location'])
        self.assertIn(b'valid four-digit examination year', response.data)

    def test_student_can_upload_a_passport_photo(self):
        with app.app_context():
            self.create_admitted_student(
                'Ada', 'ada.photo@example.com', '54323', 'JSS 1'
            )
            db.session.commit()

        student_client = app.test_client()
        student_client.post(
            '/studentlogin',
            data={'email': 'ada.photo@example.com', 'admission_id': '54323'},
        )
        previous_upload_folder = app.config['UPLOAD_FOLDER']
        try:
            with tempfile.TemporaryDirectory() as temporary_root:
                upload_folder = os.path.join(temporary_root, 'missing', 'uploads')
                app.config['UPLOAD_FOLDER'] = upload_folder
                response = student_client.post(
                    '/passport',
                    data={'passport': (io.BytesIO(b'photo-bytes'), 'portrait.png')},
                    content_type='multipart/form-data',
                )
                self.assertEqual(response.status_code, 302)
                with app.app_context():
                    student = admitted.query.filter_by(
                        email='ada.photo@example.com'
                    ).one()
                    uploaded_filename = student.passport_filename
                    self.assertTrue(os.path.isfile(
                        os.path.join(upload_folder, uploaded_filename)
                    ))
                    self.assertTrue(os.path.isdir(upload_folder))

                public_client = app.test_client()
                response = public_client.get(f'/uploads/{uploaded_filename}')
                self.assertEqual(response.status_code, 404)

                response = student_client.get(
                    f'/uploads/{uploaded_filename}'
                )
                self.assertEqual(response.status_code, 200)
                response.close()

                response = student_client.get('/passport')
                self.assertEqual(response.status_code, 200)
                self.assertIn(uploaded_filename.encode(), response.data)
                self.assertIn(b'class="topbar-avatar" src="/uploads/', response.data)
                response = student_client.get('/Biodata')
                self.assertIn(b'id="portal-theme"', response.data)
                self.assertIn(b'class="profile-identity"', response.data)
                self.assertIn(b'Use device setting', response.data)
                response = student_client.post(
                    '/passport',
                    data={'passport': (io.BytesIO(b'bad'), 'portrait.pdf')},
                    content_type='multipart/form-data',
                )
                self.assertEqual(response.status_code, 302)
                response = student_client.get(response.headers['Location'])
                self.assertIn(b'Upload a JPG, PNG, or GIF image', response.data)
        finally:
            app.config['UPLOAD_FOLDER'] = previous_upload_folder

    def test_uploaded_admission_documents_require_admin_access(self):
        with app.app_context():
            applicant = portal(
                username='private.documents',
                email='private.documents@example.com',
                firstName='Private',
                lastName='Applicant',
                dob='2015-01-01',
                gender='F',
                birth_certificate='birth-document.pdf',
                payment_evidence='payment-document.pdf',
                state_origin='Lagos',
                entry_class='JSS 1',
                entry_session='2026/2027',
                recent_result='result-document.pdf',
                phone_number='08000000000',
                address='School Road',
                admission_id='54324',
                guardian_name='Parent Name',
            )
            db.session.add(applicant)
            db.session.commit()

        public_client = app.test_client()
        previous_upload_folder = app.config['UPLOAD_FOLDER']
        try:
            with tempfile.TemporaryDirectory() as upload_folder:
                app.config['UPLOAD_FOLDER'] = upload_folder
                with open(
                    os.path.join(upload_folder, 'birth-document.pdf'),
                    'wb',
                ) as uploaded_file:
                    uploaded_file.write(b'private admission document')

                response = public_client.get('/uploads/birth-document.pdf')
                self.assertEqual(response.status_code, 404)

                admin = app.test_client()
                admin.post(
                    '/schoolAdmin',
                    data={'admin_id': '2025', 'password': 'victor1'},
                )
                response = admin.get('/uploads/birth-document.pdf')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data, b'private admission document')
                response.close()
        finally:
            app.config['UPLOAD_FOLDER'] = previous_upload_folder

    def test_staff_uploads_class_scoped_pdf_and_students_download_only_their_class(self):
        with app.app_context():
            self.create_admitted_student(
                'Ada', 'ada.library@example.com', '43001', 'JSS 1'
            )
            self.create_admitted_student(
                'Ben', 'ben.library@example.com', '43002', 'JSS 2'
            )
            teacher = Staff(
                staff_id='STAFF-LIBRARY',
                full_name='Library Teacher',
                email='library.teacher@example.com',
                password_hash=hash_password('teacher-pass-1'),
            )
            db.session.add(teacher)
            db.session.commit()

        previous_folder = app.config['LIBRARY_UPLOAD_FOLDER']
        try:
            with tempfile.TemporaryDirectory() as library_folder:
                app.config['LIBRARY_UPLOAD_FOLDER'] = library_folder
                teacher_client = app.test_client()
                teacher_client.post(
                    '/schoolAdmin',
                    data={'admin_id': 'STAFF-LIBRARY', 'password': 'teacher-pass-1'},
                )
                response = teacher_client.get('/staff/library')
                self.assertEqual(response.status_code, 200)
                self.assertIn(b'Upload PDF for a class', response.data)
                self.assertIn(b'JSS 1', response.data)

                response = teacher_client.post(
                    '/staff/library',
                    data={
                        'class_name': 'JSS 1',
                        'course_title': 'Mathematics — Fractions',
                        'description': 'Practice these examples.',
                        'pdf': (io.BytesIO(b'%PDF-1.4\nsample pdf content'), 'lesson.pdf'),
                    },
                    content_type='multipart/form-data',
                )
                self.assertEqual(response.status_code, 302)
                with app.app_context():
                    resource = LibraryResource.query.one()
                    self.assertEqual(resource.class_name, 'JSS 1')
                    self.assertEqual(resource.course_title, 'Mathematics — Fractions')
                    resource_id = resource.id
                    stored_file = os.path.join(library_folder, resource.filename)
                    self.assertTrue(os.path.isfile(stored_file))

                ada_client = app.test_client()
                ada_client.post(
                    '/studentlogin',
                    data={'email': 'ada.library@example.com', 'admission_id': '43001'},
                )
                response = ada_client.get('/library')
                self.assertEqual(response.status_code, 200)
                self.assertIn('Mathematics — Fractions'.encode(), response.data)
                self.assertIn(b'class="library-resource-reader"', response.data)
                self.assertIn(b'class="library-resource-card"', response.data)
                self.assertNotIn(b'id="library-empty"', response.data)
                self.assertNotIn(b'Download PDF', response.data)
                stylesheet = ada_client.get('/static/css/library.css')
                self.assertEqual(stylesheet.status_code, 200)
                self.assertIn(b'.invoice-empty[hidden]', stylesheet.data)
                stylesheet.close()
                self.assertNotIn(b'studyqueries.com', response.data)
                response = ada_client.get(f'/library/{resource_id}/download')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data, b'%PDF-1.4\nsample pdf content')
                self.assertIn('inline;', response.headers['Content-Disposition'])
                response.close()

                ben_client = app.test_client()
                ben_client.post(
                    '/studentlogin',
                    data={'email': 'ben.library@example.com', 'admission_id': '43002'},
                )
                response = ben_client.get('/library')
                self.assertEqual(response.status_code, 200)
                self.assertNotIn(b'Mathematics', response.data)
                response = ben_client.get(f'/library/{resource_id}/download')
                self.assertEqual(response.status_code, 404)

                response = teacher_client.post(
                    '/staff/library',
                    data={
                        'class_name': 'JSS 2',
                        'course_title': 'Not a PDF',
                        'pdf': (io.BytesIO(b'this is not a PDF'), 'document.pdf'),
                    },
                    content_type='multipart/form-data',
                )
                self.assertEqual(response.status_code, 302)
                response = teacher_client.get('/staff/library')
                self.assertIn(b'not a valid PDF document', response.data)
                with app.app_context():
                    self.assertEqual(LibraryResource.query.count(), 1)
        finally:
            app.config['LIBRARY_UPLOAD_FOLDER'] = previous_folder

    def test_teacher_enters_roster_marks_admin_approves_class_and_students_view(self):
        with app.app_context():
            teacher = Staff(
                staff_id='STAFF-01',
                full_name='Ada Teacher',
                email='ada@example.com',
                password_hash=hash_password('teacher-pass-1'),
            )
            db.session.add(teacher)
            self.create_admitted_student(
                'Ada', 'ada.marks@example.com', '10001', 'JSS 1'
            )
            self.create_admitted_student(
                'Ben', 'ben.marks@example.com', '10002', 'JSS 1'
            )
            self.create_admitted_student(
                'Cy', 'cy.marks@example.com', '10003', 'JSS 2'
            )
            db.session.add(Jss1(
                classe='JSS 1',
                term='first',
                subject='Science',
                techername='Ada Teacher',
                date=date(2026, 10, 15),
                time=time(9, 30),
            ))
            db.session.add(Jss1(
                classe='JSS 1',
                term='first',
                subject='Mathematics',
                techername='Ada Teacher',
                date=date(2026, 10, 15),
                time=time(10, 30),
            ))
            db.session.commit()
            lesson_ids = {
                lesson.subject: lesson.id for lesson in Jss1.query.order_by(Jss1.id).all()
            }

        teacher_client = app.test_client()
        teacher_client.post(
            '/schoolAdmin',
            data={'admin_id': 'STAFF-01', 'password': 'teacher-pass-1'},
        )
        response = teacher_client.get('/staff/results')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Science', response.data)
        self.assertIn(b'Mathematics', response.data)

        response = teacher_client.get(
            '/staff/results?class=jss1&term=first&subject=Science'
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Ada Student', response.data)
        self.assertIn(b'Ben Student', response.data)
        self.assertNotIn(b'Cy Student', response.data)
        self.assertIn(b'CA scores', response.data)
        self.assertIn(b'>CA 1<', response.data)
        self.assertIn(b'>CA 2<', response.data)
        self.assertIn(b'>CA 3<', response.data)
        self.assertIn(b'>Exam<', response.data)
        self.assertIn(b'name="ca1_score_1"', response.data)
        self.assertIn(b'>Grade<', response.data)
        self.assertIn(b'Grade calculated automatically from total', response.data)
        self.assertNotIn(b'name="grade_1"', response.data)
        self.assertNotIn(b'max="50"', response.data)
        self.assertNotIn(b'max="100"', response.data)

        response = teacher_client.post(
            f'/staff/results/jss1/{lesson_ids["Science"]}',
            data={
                'ca1_score_1': '150.01',
                'exam_score_1': '300.01',
                'ca1_score_2': '140',
            },
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertEqual(CourseGrade.query.count(), 0)

        response = teacher_client.post(
            f'/staff/results/jss1/{lesson_ids["Science"]}',
            data={
                'ca1_score_1': '150.01',
                'exam_score_1': '300.01',
                'ca1_score_2': '140',
                'exam_score_2': '210',
                'grade_1': 'Fail',
                'grade_2': 'Fail',
            },
        )
        self.assertEqual(response.status_code, 302)
        response = teacher_client.post(
            f'/staff/results/jss1/{lesson_ids["Mathematics"]}',
            data={
                'ca3_score_1': '45',
                'exam_score_1': '95',
                'ca3_score_2': '48',
                'exam_score_2': '88',
            },
        )
        self.assertEqual(response.status_code, 302)
        teacher_marksheet = teacher_client.get(
            '/staff/results?class=jss1&term=first&subject=Science'
        )
        self.assertIn(b'value="150.01"', teacher_marksheet.data)
        self.assertIn(b'value="140"', teacher_marksheet.data)
        self.assertIn(b'>450.02<', teacher_marksheet.data)
        self.assertIn(b'>Excellent<', teacher_marksheet.data)

        admin_client = app.test_client()
        admin_client.post(
            '/schoolAdmin',
            data={'admin_id': '2025', 'password': 'victor1'},
        )
        dashboard_response = admin_client.get('/Adminpage')
        self.assertIn(b'Results awaiting approval', dashboard_response.data)
        self.assertIn('JSS 1 · First term'.encode(), dashboard_response.data)
        response = admin_client.get('/datatable')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Science', response.data)
        self.assertIn(b'Mathematics', response.data)
        self.assertIn(b'Approve and publish Science', response.data)
        self.assertIn(b'Approve and publish Mathematics', response.data)
        self.assertEqual(response.data.count(b'class="admin-table"'), 1)
        self.assertIn(b'<th>Course</th>', response.data)
        with app.app_context():
            self.assertEqual(CourseGrade.query.count(), 4)

        student_client = app.test_client()
        student_client.post(
            '/studentlogin',
            data={'email': 'ada.marks@example.com', 'admission_id': '10001'},
        )
        response = student_client.get('/student/results')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'No approved results yet', response.data)

        response = admin_client.post(
            '/results/approve',
            data={'timetable_class': 'jss1', 'term': 'first', 'subject': 'Science'},
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertEqual(CourseResultApproval.query.count(), 1)
            self.assertEqual(CourseGrade.query.filter_by(student_id=3).count(), 0)

        response = student_client.get('/student/results')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Science', response.data)
        self.assertEqual(response.data.count(b'class="student-report-panel"'), 1)
        self.assertEqual(response.data.count(b'class="student-score-table"'), 1)
        self.assertIn(b'<th>Class</th><th>Term</th><th>Course</th>', response.data)
        self.assertIn(b'300.01', response.data)
        self.assertIn(b'450.02', response.data)
        self.assertIn(b'>Excellent<', response.data)
        self.assertNotIn(b'Mathematics', response.data)
        self.assertNotIn(b'>45<', response.data)
        unlocked_course = teacher_client.get(
            '/staff/results?class=jss1&term=first&subject=Mathematics'
        )
        self.assertEqual(unlocked_course.status_code, 200)
        self.assertIn(b'name="exam_score_1"', unlocked_course.data)
        locked_course = teacher_client.get(
            '/staff/results?class=jss1&term=first&subject=Science'
        )
        self.assertIn(b'Science marks for JSS 1 have been approved', locked_course.data)
        self.assertNotIn(b'name="exam_score_1"', locked_course.data)
        self.assertIn(b'Select term results', response.data)
        self.assertIn(b'id="result-term"', response.data)
        self.assertIn(b'form.requestSubmit()', response.data)
        self.assertNotIn(b'View results', response.data)
        self.assertIn(b'value="first"', response.data)
        self.assertEqual(app.jinja_env.filters['score'](Decimal('30.00')), '30')
        self.assertEqual(app.jinja_env.filters['score'](Decimal('30.50')), '30.5')

        with app.app_context():
            second_term_grade = CourseGrade(
                student_id=1,
                staff_id=1,
                timetable_class='jss1',
                class_name='JSS 1',
                term='second',
                subject='Science',
                ca1_score=Decimal('20'),
                exam_score=Decimal('30'),
                grade='Pass',
            )
            db.session.add(second_term_grade)
            db.session.add(CourseResultApproval(
                timetable_class='jss1',
                class_name='JSS 1',
                term='second',
                subject='Science',
                approved_by='2025',
            ))
            db.session.commit()

        response = student_client.get('/student/results?term=second')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Second term', response.data)
        self.assertIn(b'50', response.data)
        self.assertNotIn(b'450.02', response.data)
        response = student_client.get('/student/results?term=invalid')
        self.assertIn(b'All approved terms', response.data)
        self.assertIn(b'450.02', response.data)
        self.assertIn(b'50', response.data)
        self.assertEqual(response.data.count(b'class="student-report-panel"'), 1)
        self.assertEqual(response.data.count(b'class="student-score-table"'), 1)
        self.assertIn(b'2 approved course reports across all approved terms', response.data)

        response = admin_client.get('/datatable?view=approved')
        self.assertIn(b'Approved archive', response.data)
        self.assertIn(b'Science', response.data)
        response = admin_client.post(
            '/results/approve',
            data={
                'timetable_class': 'jss1',
                'term': 'first',
                'subject': 'Mathematics',
            },
        )
        self.assertEqual(response.status_code, 302)
        response = student_client.get('/student/results')
        self.assertIn(b'Mathematics', response.data)
        self.assertIn(b'>45<', response.data)
        response = admin_client.get('/datatable?view=pending')
        self.assertIn(b'No class results are waiting for approval', response.data)

        response = teacher_client.post(
            f'/staff/results/jss1/{lesson_ids["Science"]}',
            data={
                'ca1_score_1': '30',
                'ca2_score_1': '30',
                'exam_score_1': '90',
            },
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertEqual(CourseResultApproval.query.count(), 3)
            grade = CourseGrade.query.filter_by(
                student_id=1,
                subject='Science',
                term='first',
            ).one()
            self.assertIsNone(grade.ca2_score)
            self.assertEqual(grade.total_score, Decimal('450.02'))
            self.assertEqual(grade.grade, 'Excellent')

    def test_result_grades_are_automatically_calculated_from_total(self):
        self.assertEqual(result_grade_for_total(Decimal('80')), 'Excellent')
        self.assertEqual(result_grade_for_total(Decimal('79.99')), 'Very Good')
        self.assertEqual(result_grade_for_total(Decimal('70')), 'Very Good')
        self.assertEqual(result_grade_for_total(Decimal('60')), 'Good')
        self.assertEqual(result_grade_for_total(Decimal('50')), 'Pass')
        self.assertEqual(result_grade_for_total(Decimal('49.99')), 'Fail')
        self.assertIsNone(result_grade_for_total(None))

    def test_course_catalog_assigns_multiple_course_lessons_and_protects_used_courses(self):
        admin_client = app.test_client()
        admin_client.post(
            '/schoolAdmin',
            data={'admin_id': '2025', 'password': 'victor1'},
        )
        with app.app_context():
            db.session.add(Staff(
                staff_id='STAFF-COURSES',
                full_name='Ada Teacher',
                email='ada.courses@example.com',
                password_hash=hash_password('teacher-pass-1'),
            ))
            db.session.commit()

        for name in ('Mathematics', 'Science', 'Unused course'):
            response = admin_client.post(
                '/admin/courses',
                data={'action': 'add', 'name': name},
            )
            self.assertEqual(response.status_code, 302)

        with app.app_context():
            mathematics = CourseCatalog.query.filter_by(name='Mathematics').one()
            science = CourseCatalog.query.filter_by(name='Science').one()
            unused = CourseCatalog.query.filter_by(name='Unused course').one()
            mathematics_id, science_id, unused_id = mathematics.id, science.id, unused.id

        response = admin_client.post(
            '/admin/courses',
            data={
                'action': 'assign',
                'teacher': 'Ada Teacher',
                'term': 'first',
                'course_id[]': [str(mathematics_id), str(science_id)],
                'classe[]': ['jss1', 'jss2'],
                'date[]': ['2026-11-02', '2026-11-03'],
                'time[]': ['09:00', '10:00'],
            },
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertEqual(Jss1.query.one().subject, 'Mathematics')
            self.assertEqual(Jss1.query.one().techername, 'Ada Teacher')
            self.assertEqual(Jss2.query.one().subject, 'Science')

        response = admin_client.post(
            '/admin/courses',
            data={'action': 'delete', 'course_id': str(mathematics_id)},
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertIsNotNone(db.session.get(CourseCatalog, mathematics_id))

        response = admin_client.post(
            '/admin/courses',
            data={'action': 'delete', 'course_id': str(unused_id)},
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertIsNone(db.session.get(CourseCatalog, unused_id))

    def test_application_sends_confirmation_after_persisting_application(self):
        session_name = f'{date.today().year}/{date.today().year + 1}'
        form_data = {
            'username': 'ada.student',
            'firstName': 'Ada',
            'lastName': 'Student',
            'email': 'ada.application@example.com',
            'dob': '2015-01-01',
            'state_origin': 'Lagos',
            'gender': 'F',
            'entry_class': 'JSS 1',
            'entry_session': session_name,
            'phone_number': '08000000000',
            'address': 'School Road',
            'admission_id': '54321',
            'guardian_name': 'Parent Name',
            'birth_certificate': (io.BytesIO(b'birth document'), 'birth.pdf'),
            'recent_result': (io.BytesIO(b'result document'), 'result.pdf'),
        }
        with tempfile.TemporaryDirectory() as upload_dir:
            with patch.dict(app.config, {'UPLOAD_FOLDER': upload_dir}):
                response = app.test_client().post(
                    '/apply',
                    data=form_data,
                    content_type='multipart/form-data',
                )
        self.assertEqual(response.status_code, 302)
        self.email_mock.assert_called_once()
        self.assertEqual(self.email_mock.call_args.args[0], 'ada.application@example.com')
        self.assertIn('awaiting review', self.email_mock.call_args.args[2])
        with app.app_context():
            application = portal.query.filter_by(email='ada.application@example.com').first()
            self.assertIsNotNone(application)
            self.assertEqual(application.payment_evidence, '')

    def test_email_sender_uses_configured_ssl_and_sends_html_and_plain_text(self):
        app.config.update(
            MAIL_SERVER='smtp.example.invalid',
            MAIL_PORT=465,
            MAIL_USERNAME='test-user',
            MAIL_PASSWORD='test-password',
            MAIL_SENDER='school@example.invalid',
            MAIL_USE_SSL=True,
            MAIL_USE_TLS=False,
        )
        with patch('app.smtplib.SMTP_SSL') as smtp_constructor:
            smtp = smtp_constructor.return_value.__enter__.return_value
            self.assertTrue(send_email('student@example.invalid', 'Welcome', 'Hello student'))

        smtp_constructor.assert_called_once()
        smtp.login.assert_called_once_with('test-user', 'test-password')
        sent_message = smtp.sendmail.call_args.args[2]
        self.assertIn('text/plain', sent_message)
        self.assertIn('text/html', sent_message)

    def test_staff_password_reset_code_updates_the_hashed_login_password(self):
        with app.app_context():
            db.session.add(Staff(
                staff_id='STAFF-RESET',
                full_name='Reset Teacher',
                email='reset.teacher@example.com',
                password_hash=hash_password('old-password'),
            ))
            db.session.commit()

        client = app.test_client()
        response = client.post(
            '/forgot',
            data={'email': 'reset.teacher@example.com'},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Enter your reset code', response.data)
        self.email_mock.assert_called_once()
        code_match = re.search(r'code is ([0-9]{6})', self.email_mock.call_args.args[2])
        self.assertIsNotNone(code_match)
        code = code_match.group(1)

        response = client.post('/reset', data={'code': code})
        self.assertEqual(response.status_code, 302)
        self.assertIn('/resetpassword', response.headers['Location'])
        response = client.get('/resetpassword')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Choose a new password', response.data)

        response = client.post(
            '/resetpassword',
            data={'password': 'new-password-1', 'confirm_password': 'different-password'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Passwords do not match', response.data)

        response = client.post(
            '/resetpassword',
            data={'password': 'new-password-1', 'confirm_password': 'new-password-1'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/schoolAdmin', response.headers['Location'])
        with app.app_context():
            staff = Staff.query.filter_by(staff_id='STAFF-RESET').one()
            self.assertTrue(bcrypt.check_password_hash(staff.password_hash, 'new-password-1'))
            self.assertEqual(PasswordResetChallenge.query.count(), 0)

        response = client.post(
            '/schoolAdmin',
            data={'admin_id': 'STAFF-RESET', 'password': 'new-password-1'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/tasks', response.headers['Location'])

    def test_admission_tracker_shows_pending_and_approved_applications(self):
        session_name = f'{date.today().year}/{date.today().year + 1}'
        with app.app_context():
            db.session.add(portal(
                username='pending.applicant',
                email='pending.status@example.com',
                firstName='Pending',
                lastName='Applicant',
                dob='2015-01-01',
                gender='F',
                birth_certificate='birth.pdf',
                payment_evidence='payment.pdf',
                state_origin='Lagos',
                entry_class='JSS 1',
                entry_session=session_name,
                recent_result='result.pdf',
                phone_number='08000000000',
                address='School Road',
                admission_id='71234',
                guardian_name='Parent Name',
            ))
            self.create_admitted_student(
                'Approved', 'approved.status@example.com', '81234', 'JSS 2'
            )
            db.session.commit()

        client = app.test_client()
        response = client.get('/checkadmin')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Application reference or email', response.data)
        self.assertIn(f'value="{session_name}"'.encode(), response.data)

        response = client.post(
            '/checkadmin',
            data={'lookup': 'pending.status@example.com', 'entry_session': session_name},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Application received', response.data)
        self.assertIn(b'Under review', response.data)
        self.assertIn(b'71234', response.data)

        response = client.post(
            '/checkadmin',
            data={'lookup': '81234', 'entry_session': session_name},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Admission approved', response.data)
        self.assertIn(b'Go to student sign in', response.data)

    def test_results_cannot_be_approved_until_every_course_has_student_marks(self):
        with app.app_context():
            teacher = Staff(
                staff_id='STAFF-01',
                full_name='Ada Teacher',
                email='ada@example.com',
                password_hash=hash_password('teacher-pass-1'),
            )
            student = self.create_admitted_student(
                'Ada', 'ada.incomplete@example.com', '20001', 'JSS 1'
            )
            db.session.add(teacher)
            db.session.add(Jss1(
                classe='JSS 1',
                term='first',
                subject='Science',
                techername='Ada Teacher',
                date=date(2026, 10, 15),
                time=time(9, 30),
            ))
            db.session.add(Jss1(
                classe='JSS 1',
                term='first',
                subject='Mathematics',
                techername='Ada Teacher',
                date=date(2026, 10, 15),
                time=time(10, 30),
            ))
            db.session.commit()
            student_id = student.id
            lesson_id = Jss1.query.filter_by(subject='Science').one().id

        teacher_client = app.test_client()
        teacher_client.post(
            '/schoolAdmin',
            data={'admin_id': 'STAFF-01', 'password': 'teacher-pass-1'},
        )
        teacher_client.post(
            f'/staff/results/jss1/{lesson_id}',
            data={
                f'ca2_score_{student_id}': '25',
                f'grade_{student_id}': 'Good',
            },
        )

        admin_client = app.test_client()
        admin_client.post(
            '/schoolAdmin',
            data={'admin_id': '2025', 'password': 'victor1'},
        )
        response = admin_client.post(
            '/results/approve',
            data={'timetable_class': 'jss1', 'term': 'first'},
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertEqual(CourseResultApproval.query.count(), 0)
            self.assertEqual(CourseGrade.query.count(), 0)

    def test_legacy_approval_does_not_approve_courses_without_existing_marks(self):
        with app.app_context():
            student = self.create_admitted_student(
                'Ada', 'ada.approval-migration@example.com', '44001', 'JSS 1'
            )
            teacher = Staff(
                staff_id='STAFF-MIGRATION',
                full_name='Migration Teacher',
                email='migration.teacher@example.com',
                password_hash=hash_password('teacher-pass-1'),
            )
            db.session.add_all([
                teacher,
                Jss1(
                    classe='JSS 1',
                    term='first',
                    subject='Existing course',
                    techername='Migration Teacher',
                    date=date(2026, 10, 15),
                    time=time(9, 30),
                ),
                Jss1(
                    classe='JSS 1',
                    term='first',
                    subject='New course',
                    techername='Migration Teacher',
                    date=date(2026, 10, 15),
                    time=time(10, 30),
                ),
                ResultApproval(
                    timetable_class='jss1',
                    class_name='JSS 1',
                    term='first',
                    approved_by='2025',
                ),
            ])
            db.session.flush()
            db.session.add(CourseGrade(
                student_id=student.id,
                staff_id=teacher.id,
                timetable_class='jss1',
                class_name='JSS 1',
                term='first',
                subject='Existing course',
                ca1_score=20,
                exam_score=60,
            ))
            db.session.add(CourseResultApproval(
                timetable_class='jss1',
                class_name='JSS 1',
                term='first',
                subject='Empty stale course',
                approved_by='2025',
            ))
            db.session.flush()

            changed = migrate_result_approvals()
            db.session.commit()

            self.assertTrue(changed)
            self.assertEqual(ResultApproval.query.count(), 0)
            self.assertIsNotNone(CourseResultApproval.query.filter_by(
                subject='Existing course',
            ).first())
            self.assertIsNone(CourseResultApproval.query.filter_by(
                subject='New course',
            ).first())
            self.assertIsNone(CourseResultApproval.query.filter_by(
                subject='Empty stale course',
            ).first())

    def test_admin_can_edit_and_delete_fee_rates(self):
        with app.app_context():
            schedule = FeeSchedule(
                class_name='JSS 1',
                fee_type='Tuition',
                amount=Decimal('10000.00'),
            )
            db.session.add(schedule)
            db.session.commit()
            schedule_id = schedule.id

        admin_client = app.test_client()
        admin_client.post(
            '/schoolAdmin',
            data={'admin_id': '2025', 'password': 'victor1'},
        )
        response = admin_client.get('/fees')
        self.assertIn(b'Edit rate', response.data)
        self.assertIn(b'Delete', response.data)
        response = admin_client.post(
            '/fees',
            data={
                'action': 'update_schedule',
                'schedule_id': str(schedule_id),
                'fee_type': 'Tuition and materials',
                'amount': '15000',
            },
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            schedule = db.session.get(FeeSchedule, schedule_id)
            self.assertEqual(schedule.fee_type, 'Tuition and materials')
            self.assertEqual(schedule.amount, Decimal('15000.00'))

        response = admin_client.post(
            '/fees',
            data={'action': 'delete_schedule', 'schedule_id': str(schedule_id)},
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertEqual(FeeSchedule.query.count(), 0)

    def test_admin_can_pause_student_and_staff_portals(self):
        with app.app_context():
            student = self.create_admitted_student(
                'Ada', 'ada.portal@example.com', '90001', 'JSS 1'
            )
            staff = Staff(
                staff_id='STAFF-PORTAL',
                full_name='Portal Teacher',
                email='portal@example.com',
                password_hash=hash_password('teacher-pass-1'),
            )
            db.session.add(staff)
            db.session.commit()

        admin_client = app.test_client()
        admin_client.post(
            '/schoolAdmin',
            data={'admin_id': '2025', 'password': 'victor1'},
        )
        response = admin_client.post(
            '/admin/portal-settings',
            data={'student': 'disabled', 'staff': 'disabled'},
        )
        self.assertEqual(response.status_code, 302)

        student_client = app.test_client()
        response = student_client.post(
            '/studentlogin',
            data={'email': 'ada.portal@example.com', 'admission_id': '90001'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'temporarily unavailable', response.data)
        self.assertNotIn(b'<form class="login-form"', response.data)

        staff_client = app.test_client()
        response = staff_client.post(
            '/schoolAdmin',
            data={'admin_id': 'STAFF-PORTAL', 'password': 'teacher-pass-1'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'staff portal is temporarily unavailable', response.data)

        response = admin_client.get('/staff-management')
        self.assertIn(b'Save portal settings', response.data)
        self.assertIn(b'value="disabled" selected', response.data)
        response = admin_client.post(
            '/admin/portal-settings',
            data={'student': 'enabled', 'staff': 'enabled'},
        )
        self.assertEqual(response.status_code, 302)
        student_client.post(
            '/studentlogin',
            data={'email': 'ada.portal@example.com', 'admission_id': '90001'},
        )
        self.assertEqual(student_client.get('/dashboard').status_code, 200)

    def test_admin_sets_class_rates_and_student_only_sees_their_invoices(self):
        with app.app_context():
            jss_student = self.create_admitted_student(
                'Ada', 'ada.student@example.com', '12345', 'JSS 1'
            )
            sss_student = self.create_admitted_student(
                'Ben', 'ben.student@example.com', '67890', 'SSS 1'
            )
            db.session.commit()
            jss_student_id = jss_student.id
            sss_student_id = sss_student.id

        admin_client = app.test_client()
        admin_client.post(
            '/schoolAdmin',
            data={'admin_id': '2025', 'password': 'victor1'},
        )
        for class_name, amount in (('JSS 1', '125000'), ('SSS 1', '175000')):
            response = admin_client.post(
                '/fees',
                data={
                    'action': 'save_schedule',
                    'class_name': class_name,
                    'fee_type': 'Tuition',
                    'amount': amount,
                },
            )
            self.assertEqual(response.status_code, 302)

        with app.app_context():
            jss_schedule = FeeSchedule.query.filter_by(class_name='JSS 1').one()
            sss_schedule = FeeSchedule.query.filter_by(class_name='SSS 1').one()
            jss_schedule_id = jss_schedule.id
            sss_schedule_id = sss_schedule.id
            self.assertEqual(jss_schedule.amount, 125000)
            self.assertEqual(sss_schedule.amount, 175000)

        for student_id, schedule_id in (
            (jss_student_id, jss_schedule_id),
            (sss_student_id, sss_schedule_id),
        ):
            response = admin_client.post(
                '/fees',
                data={
                    'action': 'issue_invoice',
                    'student_id': str(student_id),
                    'schedule_id': str(schedule_id),
                    'due_date': '2026-11-01',
                },
            )
            self.assertEqual(response.status_code, 302)

        response = admin_client.post(
            '/fees',
            data={
                'action': 'issue_invoice',
                'student_id': str(jss_student_id),
                'schedule_id': str(sss_schedule_id),
            },
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            invoices = FeeInvoice.query.order_by(FeeInvoice.student_id).all()
            self.assertEqual(len(invoices), 2)
            self.assertEqual(invoices[0].amount, 125000)
            self.assertEqual(invoices[1].amount, 175000)
            self.assertEqual(invoices[0].school_session, '2026/2027')

        ada_client = app.test_client()
        ada_client.post(
            '/studentlogin',
            data={'email': 'ada.student@example.com', 'admission_id': '12345'},
        )
        response = ada_client.get('/my-invoices')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'125,000.00', response.data)
        self.assertNotIn(b'175,000.00', response.data)
        self.assertNotIn(b'Ben Student', response.data)

        ben_client = app.test_client()
        ben_client.post(
            '/studentlogin',
            data={'email': 'ben.student@example.com', 'admission_id': '67890'},
        )
        response = ben_client.get('/my-invoices')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'175,000.00', response.data)
        self.assertNotIn(b'125,000.00', response.data)

    def test_new_student_sees_prior_class_wide_invoice_but_not_individual_invoice(self):
        with app.app_context():
            existing_student = self.create_admitted_student(
                'Ada', 'ada.class-fees@example.com', '45001', 'JSS 1'
            )
            db.session.add(FeeSchedule(
                class_name='JSS 1',
                fee_type='Tuition',
                amount=Decimal('125000.00'),
            ))
            db.session.commit()
            existing_student_id = existing_student.id
            schedule_id = FeeSchedule.query.one().id

        admin_client = app.test_client()
        admin_client.post(
            '/schoolAdmin',
            data={'admin_id': '2025', 'password': 'victor1'},
        )
        response = admin_client.post(
            '/fees',
            data={
                'action': 'issue_class_invoices',
                'class_name': 'JSS 1',
                'schedule_id': str(schedule_id),
                'description': 'Shared JSS 1 tuition invoice',
            },
        )
        self.assertEqual(response.status_code, 302)
        admin_client.post(
            '/fees',
            data={
                'action': 'issue_invoice',
                'student_id': str(existing_student_id),
                'schedule_id': str(schedule_id),
                'description': 'Private one-student adjustment',
            },
        )

        with app.app_context():
            new_student = self.create_admitted_student(
                'Ben', 'ben.new-class-fees@example.com', '45002', 'JSS 1'
            )
            db.session.commit()
            new_student_id = new_student.id

        student_client = app.test_client()
        student_client.post(
            '/studentlogin',
            data={
                'email': 'ben.new-class-fees@example.com',
                'admission_id': '45002',
            },
        )
        response = student_client.get('/my-invoices')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Shared JSS 1 tuition invoice', response.data)
        self.assertNotIn(b'Private one-student adjustment', response.data)

        with app.app_context():
            private_invoice_id = FeeInvoice.query.filter_by(
                description='Private one-student adjustment'
            ).one().id
        response = admin_client.post(
            '/fees',
            data={
                'action': 'share_invoice',
                'invoice_id': str(private_invoice_id),
            },
        )
        self.assertEqual(response.status_code, 302)
        response = student_client.get('/my-invoices')
        self.assertIn(b'Private one-student adjustment', response.data)
        self.assertEqual(response.data.count(b'class="student-invoice-card"'), 1)
        self.assertEqual(response.data.count(b'class="student-invoice-entry"'), 2)

        with app.app_context():
            new_invoice_rows = student_class_invoices(db.session.get(admitted, new_student_id))
            self.assertEqual(len(new_invoice_rows), 2)
            self.assertTrue(all(invoice.invoice_batch_id for invoice in new_invoice_rows))

    def test_invoice_page_backfills_class_rate_and_shared_invoices_for_existing_student(self):
        with app.app_context():
            existing_student = self.create_admitted_student(
                'Ada', 'ada.invoice-backfill@example.com', '45003', 'JSS 1'
            )
            db.session.commit()
            student_id = existing_student.id
            db.session.add(FeeSchedule(
                class_name='JSS 1',
                fee_type='Tuition',
                amount=Decimal('125000.00'),
            ))
            db.session.commit()

        admin = app.test_client()
        admin.post(
            '/schoolAdmin',
            data={'admin_id': '2025', 'password': 'victor1'},
        )
        with app.app_context():
            schedule_id = FeeSchedule.query.one().id
        response = admin.post(
            '/fees',
            data={
                'action': 'issue_class_invoices',
                'class_name': 'JSS 1',
                'schedule_id': str(schedule_id),
                'description': 'Existing class tuition invoice',
            },
        )
        self.assertEqual(response.status_code, 302)

        student = app.test_client()
        student.post(
            '/studentlogin',
            data={
                'email': 'ada.invoice-backfill@example.com',
                'admission_id': '45003',
            },
        )
        response = student.get('/my-invoices')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Existing class tuition invoice', response.data)
        self.assertIn(b'Tuition', response.data)

        with app.app_context():
            student_invoices = FeeInvoice.query.filter_by(
                student_id=student_id
            ).all()
            self.assertEqual(len(student_invoices), 1)
            self.assertIsNotNone(student_invoices[0].invoice_batch_id)

    def test_moving_student_into_class_immediately_adds_existing_class_invoices(self):
        with app.app_context():
            existing_student = self.create_admitted_student(
                'Ada', 'ada.existing-class-invoice@example.com', '45004', 'JSS 1'
            )
            moved_student = self.create_admitted_student(
                'Ben', 'ben.moved-class-invoice@example.com', '45005', 'JSS 2'
            )
            db.session.add(FeeSchedule(
                class_name='JSS 1',
                fee_type='Class tuition',
                amount=Decimal('125000.00'),
            ))
            db.session.commit()
            moved_student_id = moved_student.id
            schedule_id = FeeSchedule.query.one().id

        admin = app.test_client()
        admin.post(
            '/schoolAdmin',
            data={'admin_id': '2025', 'password': 'victor1'},
        )
        response = admin.post(
            '/fees',
            data={
                'action': 'issue_class_invoices',
                'class_name': 'JSS 1',
                'schedule_id': str(schedule_id),
                'description': 'Already issued JSS 1 fee',
            },
        )
        self.assertEqual(response.status_code, 302)

        response = admin.post(
            f'/students/{moved_student_id}/class',
            data={'entry_class': 'JSS 1'},
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            moved_invoice = FeeInvoice.query.filter_by(
                student_id=moved_student_id,
                description='Already issued JSS 1 fee',
            ).one()
            self.assertIsNotNone(moved_invoice.invoice_batch_id)
            self.assertEqual(moved_invoice.school_session, '2026/2027')

        student = app.test_client()
        student.post(
            '/studentlogin',
            data={
                'email': 'ben.moved-class-invoice@example.com',
                'admission_id': '45005',
            },
        )
        response = student.get('/my-invoices')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Already issued JSS 1 fee', response.data)
        self.assertIn(b'125,000.00', response.data)

    def test_admin_can_issue_a_fee_invoice_to_every_student_in_a_class(self):
        with app.app_context():
            ada = self.create_admitted_student(
                'Ada', 'ada.class@example.com', '11111', 'JSS 1'
            )
            ben = self.create_admitted_student(
                'Ben', 'ben.class@example.com', '22222', 'JSS 1'
            )
            cy = self.create_admitted_student(
                'Cy', 'cy.class@example.com', '33333', 'JSS 2'
            )
            db.session.add(FeeSchedule(
                class_name='JSS 1',
                fee_type='Examination',
                amount=Decimal('25000.00'),
            ))
            db.session.commit()
            ada_id, ben_id, cy_id = ada.id, ben.id, cy.id
            schedule_id = FeeSchedule.query.one().id

        admin_client = app.test_client()
        admin_client.post(
            '/schoolAdmin',
            data={'admin_id': '2025', 'password': 'victor1'},
        )
        response = admin_client.post(
            '/fees',
            data={
                'action': 'issue_class_invoices',
                'class_name': 'JSS 1',
                'schedule_id': str(schedule_id),
                'due_date': '2026-11-15',
                'description': 'Term examination fee',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            [call.args[0] for call in self.email_mock.call_args_list],
            ['ada.class@example.com', 'ben.class@example.com'],
        )
        with app.app_context():
            invoices = FeeInvoice.query.order_by(FeeInvoice.student_id).all()
            self.assertEqual([invoice.student_id for invoice in invoices], [ada_id, ben_id])
            self.assertEqual(len(invoices), 2)
            self.assertTrue(all(invoice.amount == 25000 for invoice in invoices))
            self.assertTrue(all(invoice.description == 'Term examination fee' for invoice in invoices))
            self.assertTrue(all(invoice.due_date == date(2026, 11, 15) for invoice in invoices))

        response = admin_client.post(
            '/fees',
            data={
                'action': 'issue_class_invoices',
                'class_name': 'JSS 2',
                'schedule_id': str(schedule_id),
            },
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertEqual(FeeInvoice.query.count(), 2)

        ada_client = app.test_client()
        ada_client.post(
            '/studentlogin',
            data={'email': 'ada.class@example.com', 'admission_id': '11111'},
        )
        response = ada_client.get('/my-invoices')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Examination', response.data)
        self.assertIn(b'25,000.00', response.data)
        self.assertNotIn(b'Ben Student', response.data)

        cy_client = app.test_client()
        cy_client.post(
            '/studentlogin',
            data={'email': 'cy.class@example.com', 'admission_id': '33333'},
        )
        response = cy_client.get('/my-invoices')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'No invoices yet', response.data)


if __name__ == '__main__':
    unittest.main()
