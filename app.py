import ast
import hashlib
import hmac
import html
import io
import os
import random
import re
import secrets
import smtplib
import ssl
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps

import pdfkit
import PyPDF2
import requests
from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, send_file, send_from_directory, session, url_for)
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url

app = Flask(__name__)
APP_ENV = os.environ.get('APP_ENV', 'development').strip().lower()
IS_PRODUCTION = APP_ENV == 'production'
production_required_settings = (
    'SECRET_KEY',
    'DATABASE_URL',
    'ADMIN_ID',
    'ADMIN_PASSWORD',
    'MAIL_SERVER',
    'MAIL_USERNAME',
    'MAIL_PASSWORD',
)
if IS_PRODUCTION:
    missing_settings = [
        name for name in production_required_settings
        if not os.environ.get(name)
    ]
    if missing_settings:
        raise RuntimeError(
            'Production configuration is incomplete. Set: '
            + ', '.join(missing_settings)
        )
    if len(os.environ['SECRET_KEY']) < 32:
        raise RuntimeError('Production SECRET_KEY must contain at least 32 characters.')
    if len(os.environ['ADMIN_PASSWORD']) < 12:
        raise RuntimeError('Production ADMIN_PASSWORD must contain at least 12 characters.')

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'local-development-only-change-before-hosting'
app.config['ADMIN_ID'] = os.environ.get(
    'ADMIN_ID',
    '2025' if not IS_PRODUCTION else '',
)
app.config['ADMIN_PASSWORD'] = os.environ.get(
    'ADMIN_PASSWORD',
    'victor1' if not IS_PRODUCTION else '',
)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=IS_PRODUCTION,
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,
)


def load_local_mail_environment():
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if not os.path.isfile(env_path):
        return
    with open(env_path, encoding='utf-8') as env_file:
        for line in env_file:
            key, separator, value = line.strip().partition('=')
            if separator and key.startswith('MAIL_'):
                os.environ.setdefault(key, value.strip().strip('"').strip("'"))


load_local_mail_environment()

# Update the MySQL connection settings
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://root:@localhost/studentportal'
app.config['SQLALCHEMY_DATABASE_URI'] = (
    os.environ.get('DATABASE_URL') or app.config['SQLALCHEMY_DATABASE_URI']
)
database_url = make_url(app.config['SQLALCHEMY_DATABASE_URI'])
if database_url.drivername in {'mysql', 'mysql+mysqldb'}:
    database_url = database_url.set(drivername='mysql+pymysql')
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['LIBRARY_UPLOAD_FOLDER'] = os.environ.get(
    'LIBRARY_UPLOAD_FOLDER',
    os.path.join(app.root_path, 'uploads', 'library'),
)
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', '')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', '587'))
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_SENDER'] = (
    os.environ.get('MAIL_FROM')
    or os.environ.get('MAIL_SENDER')
    or app.config['MAIL_USERNAME']
)
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').strip().lower() in {
    '1', 'true', 'yes', 'on',
}
app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'false').strip().lower() in {
    '1', 'true', 'yes', 'on',
}
if IS_PRODUCTION and app.config['MAIL_USE_SSL'] and app.config['MAIL_USE_TLS']:
    raise RuntimeError('Enable either MAIL_USE_SSL or MAIL_USE_TLS, not both.')


def ensure_database_exists(database_uri):
    database_url = make_url(database_uri)
    if database_url.get_backend_name() != 'mysql':
        return

    database_name = database_url.database
    if not database_name:
        raise ValueError('DATABASE_URL must include a MySQL database name.')

    server_engine = create_engine(
        database_url.set(database=None),
        pool_pre_ping=True,
    )
    try:
        with server_engine.connect() as connection:
            quoted_database = connection.dialect.identifier_preparer.quote(
                database_name
            )
            connection.exec_driver_sql(
                f'CREATE DATABASE IF NOT EXISTS {quoted_database}'
            )
    finally:
        server_engine.dispose()


if not IS_PRODUCTION:
    ensure_database_exists(app.config['SQLALCHEMY_DATABASE_URI'])
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

class portal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    firstName = db.Column(db.String(20), nullable=False)
    lastName = db.Column(db.String(10), nullable=False)
    
    dob=db.Column(db.String(60), nullable=False)
    gender=db.Column(db.String(60), nullable=False)
    birth_certificate=db.Column(db.String(60), nullable=False)
    payment_evidence=db.Column(db.String(60), nullable=False)
    state_origin=db.Column(db.String(60), nullable=False)
    entry_class=db.Column(db.String(60), nullable=False)
    entry_session=db.Column(db.String(60), nullable=False)
    recent_result=db.Column(db.String(60), nullable=False)
    phone_number=db.Column(db.String(60), nullable=False)
    address=db.Column(db.String(60), nullable=False)
    admission_id=db.Column(db.String(60), nullable=False)
    guardian_name=db.Column(db.String(60), nullable=False) 
   
    reset_code = db.Column(db.String(6))

class admitted(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    firstName = db.Column(db.String(20), nullable=False)
    lastName = db.Column(db.String(10), nullable=False)
    
    dob=db.Column(db.String(60), nullable=False)
    gender=db.Column(db.String(60), nullable=False)
    birth_certificate=db.Column(db.String(60), nullable=False)
    payment_evidence=db.Column(db.String(60), nullable=False)
    state_origin=db.Column(db.String(60), nullable=False)
    entry_class=db.Column(db.String(60), nullable=False)
    entry_session=db.Column(db.String(60), nullable=False)
    recent_result=db.Column(db.String(60), nullable=False)
    phone_number=db.Column(db.String(60), nullable=False)
    address=db.Column(db.String(60), nullable=False)
    admission_id=db.Column(db.String(60), nullable=False)
    guardian_name=db.Column(db.String(60), nullable=False) 
    passport_filename = db.Column(db.String(120), nullable=True)
    is_graduated = db.Column(db.Boolean, nullable=False, default=False)
   
class Jss1(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    classe= db.Column(db.String(100), nullable=False)
    term= db.Column(db.String(100), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    techername = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)

class Jss2(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    classe= db.Column(db.String(100), nullable=False)
    term= db.Column(db.String(100), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    techername = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
class Jss3(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    classe= db.Column(db.String(100), nullable=False)
    term= db.Column(db.String(100), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    techername = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)

class Sss1(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    classe= db.Column(db.String(100), nullable=False)
    term= db.Column(db.String(100), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    techername = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
class Sss2(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    classe= db.Column(db.String(100), nullable=False)
    term= db.Column(db.String(100), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    techername = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)


class CourseCatalog(db.Model):
    __tablename__ = 'course_catalog'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)


TIMETABLES = {
    'jss1': Jss1,
    'jss2': Jss2,
    'jss3': Jss3,
    'sss1': Sss1,
    'sss2': Sss2,
}

TIMETABLE_CLASS_NAMES = {}


def create_grade_timetable_model(class_key):
    grade = class_key[5:-1]
    section = class_key[-1]
    return type(
        f'Grade{grade}{section.upper()}Timetable',
        (db.Model,),
        {
            '__tablename__': f'timetable_grade_{grade}_{section}',
            'id': db.Column(db.Integer, primary_key=True, autoincrement=True),
            'classe': db.Column(db.String(100), nullable=False),
            'term': db.Column(db.String(100), nullable=False),
            'subject': db.Column(db.String(100), nullable=False),
            'techername': db.Column(db.String(100), nullable=False),
            'date': db.Column(db.Date, nullable=False),
            'time': db.Column(db.Time, nullable=False),
        },
    )


for grade in range(7, 13):
    for section in ('a', 'b'):
        class_key = f'grade{grade}{section}'
        class_name = f'Grade {grade}{section.upper()}'
        TIMETABLE_CLASS_NAMES[class_key] = class_name
        TIMETABLES[class_key] = create_grade_timetable_model(class_key)

SCHOOL_CLASSES = (
    'Play Group',
    'Pre School',
    'KG 1',
    'KG 2',
    'KG 3',
    'Basic 1',
    'Basic 2',
    'Basic 3',
    'Basic 4',
    'Basic 5',
    'Basic 6',
    *(TIMETABLE_CLASS_NAMES[f'grade{grade}{section}']
      for grade in range(7, 13)
      for section in ('a', 'b')),
)
app.jinja_env.globals['SCHOOL_CLASSES'] = SCHOOL_CLASSES


class Staff(db.Model):
    __tablename__ = 'staff_accounts'

    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.String(50), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    tasks = db.relationship('StaffTask', back_populates='assigned_staff')


class PasswordResetChallenge(db.Model):
    __tablename__ = 'password_reset_challenges'

    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff_accounts.id'), nullable=False)
    code_hash = db.Column(db.String(64), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    failed_attempts = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)


class StaffTask(db.Model):
    __tablename__ = 'staff_tasks'

    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff_accounts.id'), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='pending')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    assigned_staff = db.relationship('Staff', back_populates='tasks')


class ResultUpload(db.Model):
    __tablename__ = 'result_uploads'

    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff_accounts.id'), nullable=False)
    timetable_class = db.Column(db.String(20), nullable=False)
    timetable_id = db.Column(db.Integer, nullable=False)
    classe = db.Column(db.String(100), nullable=False)
    term = db.Column(db.String(100), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    filename = db.Column(db.String(255), nullable=False, unique=True)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    teacher = db.relationship('Staff')


class CourseGrade(db.Model):
    __tablename__ = 'course_grades'
    __table_args__ = (
        db.UniqueConstraint(
            'student_id',
            'timetable_class',
            'term',
            'subject',
            name='uq_course_grade_student_class_term_subject',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('admitted.id'), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff_accounts.id'), nullable=False)
    timetable_class = db.Column(db.String(20), nullable=False)
    class_name = db.Column(db.String(100), nullable=False)
    term = db.Column(db.String(100), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    ca1_score = db.Column(db.Numeric(10, 2), nullable=True)
    ca2_score = db.Column(db.Numeric(10, 2), nullable=True)
    ca3_score = db.Column(db.Numeric(10, 2), nullable=True)
    exam_score = db.Column(db.Numeric(10, 2), nullable=True)
    grade = db.Column(db.String(30), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
    student = db.relationship('admitted')
    teacher = db.relationship('Staff')

    @property
    def total_score(self):
        scores = (self.ca1_score, self.ca2_score, self.ca3_score, self.exam_score)
        if not any(score is not None for score in scores):
            return None
        return sum((score for score in scores if score is not None), Decimal('0.00'))


class LibraryResource(db.Model):
    __tablename__ = 'library_resources'

    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff_accounts.id'), nullable=False)
    class_name = db.Column(db.String(60), nullable=False)
    course_title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    filename = db.Column(db.String(255), nullable=False, unique=True)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    teacher = db.relationship('Staff')


class ResultApproval(db.Model):
    __tablename__ = 'result_approvals'
    __table_args__ = (
        db.UniqueConstraint('timetable_class', 'term', name='uq_result_approval_class_term'),
    )

    id = db.Column(db.Integer, primary_key=True)
    timetable_class = db.Column(db.String(20), nullable=False)
    class_name = db.Column(db.String(100), nullable=False)
    term = db.Column(db.String(100), nullable=False)
    approved_by = db.Column(db.String(50), nullable=False)
    approved_at = db.Column(db.DateTime, nullable=False, default=datetime.now)


class CourseResultApproval(db.Model):
    __tablename__ = 'course_result_approvals'
    __table_args__ = (
        db.UniqueConstraint(
            'timetable_class',
            'term',
            'subject',
            name='uq_course_result_approval',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    timetable_class = db.Column(db.String(20), nullable=False)
    class_name = db.Column(db.String(100), nullable=False)
    term = db.Column(db.String(100), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    approved_by = db.Column(db.String(50), nullable=False)
    approved_at = db.Column(db.DateTime, nullable=False, default=datetime.now)


class FeeSchedule(db.Model):
    __tablename__ = 'fee_schedules'
    __table_args__ = (
        db.UniqueConstraint('class_name', 'fee_type', name='uq_fee_schedule_class_type'),
    )

    id = db.Column(db.Integer, primary_key=True)
    class_name = db.Column(db.String(60), nullable=False)
    fee_type = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)


class FeeInvoice(db.Model):
    __tablename__ = 'fee_invoices'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('admitted.id'), nullable=False)
    fee_type = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    class_name = db.Column(db.String(60), nullable=False)
    school_session = db.Column(db.String(30), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    issued_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    invoice_batch_id = db.Column(db.String(36), nullable=True)
    student = db.relationship('admitted')


class PortalSetting(db.Model):
    __tablename__ = 'portal_settings'

    key = db.Column(db.String(40), primary_key=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)


def migrate_result_approvals():
    changed = False
    for approval in ResultApproval.query.all():
        timetable_model = TIMETABLES.get(approval.timetable_class)
        if timetable_model is None:
            continue
        lessons = timetable_model.query.filter_by(term=approval.term).all()
        approved_subjects = {
            lesson.subject
            for lesson in lessons
            if re.sub(r'[^a-z0-9]', '', (lesson.classe or '').casefold())
            == approval.timetable_class
        }
        for subject in approved_subjects:
            has_marks = CourseGrade.query.filter_by(
                timetable_class=approval.timetable_class,
                term=approval.term,
                subject=subject,
            ).first()
            if not has_marks:
                continue
            course_approval = CourseResultApproval.query.filter_by(
                timetable_class=approval.timetable_class,
                term=approval.term,
                subject=subject,
            ).first()
            if course_approval is None:
                db.session.add(CourseResultApproval(
                    timetable_class=approval.timetable_class,
                    class_name=approval.class_name,
                    term=approval.term,
                    subject=subject,
                    approved_by=approval.approved_by,
                    approved_at=approval.approved_at,
                ))
                changed = True
        db.session.delete(approval)
        changed = True

    for approval in CourseResultApproval.query.all():
        has_marks = CourseGrade.query.filter_by(
            timetable_class=approval.timetable_class,
            term=approval.term,
            subject=approval.subject,
        ).first()
        if not has_marks:
            db.session.delete(approval)
            changed = True
    return changed


with app.app_context():
    db.create_all()
    admitted_columns = {
        column['name']
        for column in inspect(db.engine).get_columns(admitted.__tablename__)
    }
    if 'is_graduated' not in admitted_columns:
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                'ALTER TABLE admitted ADD COLUMN is_graduated BOOLEAN NOT NULL DEFAULT 0'
            )
    invoice_columns = {
        column['name']
        for column in inspect(db.engine).get_columns(FeeInvoice.__tablename__)
    }
    if 'invoice_batch_id' not in invoice_columns:
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                'ALTER TABLE fee_invoices ADD COLUMN invoice_batch_id VARCHAR(36) NULL'
            )
    reset_challenge_columns = {
        column['name']
        for column in inspect(db.engine).get_columns(
            PasswordResetChallenge.__tablename__
        )
    }
    if 'failed_attempts' not in reset_challenge_columns:
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                'ALTER TABLE password_reset_challenges '
                'ADD COLUMN failed_attempts INTEGER NOT NULL DEFAULT 0'
            )
    if db.engine.dialect.name == 'mysql':
        grade_columns = {
            column['name']: column['type']
            for column in inspect(db.engine).get_columns(CourseGrade.__tablename__)
        }
        for score_column in ('ca1_score', 'ca2_score', 'ca3_score', 'exam_score'):
            column_type = grade_columns.get(score_column)
            if column_type is not None and (
                getattr(column_type, 'precision', 0) < 10
                or getattr(column_type, 'scale', 0) < 2
            ):
                with db.engine.begin() as connection:
                    connection.exec_driver_sql(
                        f'ALTER TABLE course_grades MODIFY COLUMN {score_column} DECIMAL(10, 2) NULL'
                    )
    grade_columns = {
        column['name']
        for column in inspect(db.engine).get_columns(CourseGrade.__tablename__)
    }
    if 'grade' not in grade_columns:
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                'ALTER TABLE course_grades ADD COLUMN grade VARCHAR(30) NULL'
            )
    catalog_names = {
        course.name.casefold() for course in CourseCatalog.query.all()
    }
    for timetable_model in TIMETABLES.values():
        for lesson in timetable_model.query.all():
            course_name = (lesson.subject or '').strip()
            if course_name and course_name.casefold() not in catalog_names:
                db.session.add(CourseCatalog(name=course_name))
                catalog_names.add(course_name.casefold())
    migrated_approvals = migrate_result_approvals()
    if db.session.new or migrated_approvals:
        db.session.commit()


def portal_is_enabled(portal_name):
    setting = db.session.get(PortalSetting, portal_name)
    return setting.enabled if setting else True


def hash_password(password):
    return bcrypt.generate_password_hash(password).decode('utf-8')


def parse_fee_amount(value):
    try:
        amount = Decimal(value).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return amount if amount.is_finite() and amount > 0 else None


def parse_assessment_score(value, maximum=None):
    try:
        score = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not score.is_finite() or score < 0 or (maximum is not None and score > maximum):
        return None
    return score.quantize(Decimal('0.01'))


@app.template_filter('score')
def format_result_score(value):
    if value is None:
        return '—'
    return format(Decimal(value).normalize(), 'f')


def result_grade_for_total(total):
    if total is None:
        return None
    total = Decimal(total)
    if total >= Decimal('80'):
        return 'Excellent'
    if total >= Decimal('70'):
        return 'Very Good'
    if total >= Decimal('60'):
        return 'Good'
    if total >= Decimal('50'):
        return 'Pass'
    return 'Fail'


@app.template_filter('result_grade')
def format_result_grade(total):
    return result_grade_for_total(total) or '—'


def normalize_class_name(class_name):
    return re.sub(r'[^a-z0-9]', '', (class_name or '').casefold())


def ensure_student_class_invoices(student):
    student_class = normalize_class_name(student.entry_class)
    student_session = (student.entry_session or '').strip().casefold()
    if not student_class or not student_session:
        return []

    own_invoices = FeeInvoice.query.filter_by(student_id=student.id).all()
    matching_own_invoices = [
        invoice for invoice in own_invoices
        if normalize_class_name(invoice.class_name) == student_class
        and (invoice.school_session or '').strip().casefold() == student_session
    ]
    own_batch_ids = {
        invoice.invoice_batch_id
        for invoice in matching_own_invoices
        if invoice.invoice_batch_id
    }
    own_fee_types = {
        invoice.fee_type.strip().casefold()
        for invoice in matching_own_invoices
    }

    class_wide_invoices = [
        invoice
        for invoice in FeeInvoice.query.filter(
            FeeInvoice.invoice_batch_id.isnot(None),
        ).order_by(FeeInvoice.issued_at, FeeInvoice.id).all()
        if normalize_class_name(invoice.class_name) == student_class
        and (invoice.school_session or '').strip().casefold() == student_session
    ]
    invoices_by_batch = {}
    for invoice in class_wide_invoices:
        if invoice.invoice_batch_id not in own_batch_ids:
            invoices_by_batch.setdefault(invoice.invoice_batch_id, invoice)

    new_invoices = [
        FeeInvoice(
            student_id=student.id,
            fee_type=source.fee_type,
            description=source.description,
            class_name=student.entry_class,
            school_session=student.entry_session,
            amount=source.amount,
            due_date=source.due_date,
            issued_at=source.issued_at,
            invoice_batch_id=batch_id,
        )
        for batch_id, source in invoices_by_batch.items()
    ]
    own_fee_types.update(
        invoice.fee_type.strip().casefold()
        for invoice in new_invoices
    )

    class_fee_schedules = [
        schedule
        for schedule in FeeSchedule.query.order_by(FeeSchedule.fee_type).all()
        if normalize_class_name(schedule.class_name) == student_class
        and schedule.fee_type.strip().casefold() not in own_fee_types
    ]
    new_invoices.extend(
        FeeInvoice(
            student_id=student.id,
            fee_type=schedule.fee_type,
            description='Class fee rate',
            class_name=student.entry_class,
            school_session=student.entry_session,
            amount=schedule.amount,
        )
        for schedule in class_fee_schedules
    )
    if not new_invoices:
        return []

    db.session.add_all(new_invoices)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception(
            'Could not prepare class invoices for student %s',
            student.id,
        )
        raise

    for invoice in new_invoices:
        email_fee_invoice(invoice)
    return new_invoices


def student_class_invoices(student):
    ensure_student_class_invoices(student)
    student_class = normalize_class_name(student.entry_class)
    student_session = (student.entry_session or '').strip().casefold()
    own_invoices = FeeInvoice.query.filter_by(student_id=student.id).order_by(
        FeeInvoice.issued_at.desc()
    ).all()
    visible_invoices = {
        invoice.id: invoice
        for invoice in own_invoices
        if normalize_class_name(invoice.class_name) == student_class
        and (invoice.school_session or '').strip().casefold() == student_session
    }

    if student_class and student_session:
        shared_invoices = FeeInvoice.query.filter(
            FeeInvoice.invoice_batch_id.isnot(None),
        ).order_by(FeeInvoice.issued_at.desc()).all()
        own_batch_ids = {
            invoice.invoice_batch_id
            for invoice in visible_invoices.values()
            if invoice.invoice_batch_id
        }
        for invoice in shared_invoices:
            if (
                normalize_class_name(invoice.class_name) != student_class
                or (invoice.school_session or '').strip().casefold() != student_session
                or invoice.invoice_batch_id in own_batch_ids
            ):
                continue
            visible_invoices.setdefault(invoice.id, invoice)
            own_batch_ids.add(invoice.invoice_batch_id)

    return sorted(
        visible_invoices.values(),
        key=lambda invoice: (invoice.issued_at, invoice.id),
        reverse=True,
    )


def email_fee_invoice(invoice):
    student = invoice.student
    receiver_email = (student.email or '').strip()
    if not receiver_email:
        app.logger.warning('Fee invoice %s has no student email address.', invoice.id)
        return False

    due_date = invoice.due_date.strftime('%b %d, %Y') if invoice.due_date else 'Not specified'
    message = (
        f"Dear {student.firstName} {student.lastName},\n\n"
        "Please review the fee invoice issued to you by Florence Court International Schools.\n\n"
        f"Invoice reference: {invoice.id}\n"
        f"Fee: {invoice.fee_type}\n"
        f"Amount: NGN {invoice.amount:,.2f}\n"
        f"Class: {invoice.class_name}\n"
        f"School session: {invoice.school_session}\n"
        f"Due date: {due_date}\n"
    )
    if invoice.description:
        message += f"\nNote: {invoice.description}\n"
    message += (
        "\nIf you have already paid or have a question about this fee, please contact "
        "the school finance office and include the invoice reference above.\n\n"
        "Florence Court International Schools"
    )
    return send_email(
        receiver_email,
        f"Fee notice: {invoice.fee_type} (Invoice #{invoice.id})",
        message,
    )


def student_passport_url(student):
    filename = student.passport_filename or ''
    if (
        filename
        and secure_filename(filename) == filename
        and os.path.isfile(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    ):
        return url_for('uploaded_file', filename=filename)
    return url_for('static', filename='img/user.jpg')


@app.context_processor
def student_profile_helpers():
    return {'student_passport_url': student_passport_url}


def assigned_result_courses(staff):
    courses = {}
    for class_key, timetable_model in TIMETABLES.items():
        lessons = timetable_model.query.filter_by(
            techername=staff.full_name
        ).order_by(timetable_model.date, timetable_model.time, timetable_model.id).all()
        for lesson in lessons:
            key = (class_key, lesson.term.casefold(), lesson.subject.casefold())
            if key not in courses:
                courses[key] = {
                    'class_key': class_key,
                    'class_name': lesson.classe,
                    'term': lesson.term,
                    'subject': lesson.subject,
                    'timetable_id': lesson.id,
                }
    return sorted(
        courses.values(),
        key=lambda course: (
            course['class_name'].casefold(),
            course['term'].casefold(),
            course['subject'].casefold(),
        ),
    )


def result_roster(class_name):
    class_key = normalize_class_name(class_name)
    return [
        student
        for student in admitted.query.order_by(admitted.firstName, admitted.lastName).all()
        if normalize_class_name(student.entry_class) == class_key
    ]


def class_course_grades(class_key, term, subject, students):
    roster_ids = {student.id for student in students}
    if not roster_ids:
        return []
    return [
        grade
        for grade in CourseGrade.query.filter_by(
            timetable_class=class_key,
            term=term,
            subject=subject,
        ).order_by(CourseGrade.student_id).all()
        if grade.student_id in roster_ids
        and normalize_class_name(grade.class_name) == class_key
    ]


def class_term_result_summary(class_key, term, class_name):
    timetable_model = TIMETABLES[class_key]
    lessons = timetable_model.query.filter_by(term=term).order_by(
        timetable_model.subject, timetable_model.id
    ).all()
    unique_subjects = {}
    for lesson in lessons:
        if normalize_class_name(lesson.classe) != class_key:
            continue
        unique_subjects.setdefault(lesson.subject.casefold(), lesson.subject)

    students = result_roster(class_name)
    course_results = []
    for subject in sorted(unique_subjects.values(), key=str.casefold):
        course_grades = class_course_grades(class_key, term, subject, students)
        complete_student_ids = {
            grade.student_id
            for grade in course_grades
            if result_grade_for_total(grade.total_score)
            and any(score is not None for score in (
                grade.ca1_score,
                grade.ca2_score,
                grade.ca3_score,
            ))
            and grade.exam_score is not None
        }
        approval = CourseResultApproval.query.filter_by(
            timetable_class=class_key,
            term=term,
            subject=subject,
        ).first()
        course_results.append({
            'subject': subject,
            'grades': course_grades,
            'required_count': len(students),
            'completed_count': len(complete_student_ids),
            'missing_count': len(students) - len(complete_student_ids),
            'approved': approval is not None,
            'approval': approval,
        })

    required_count = sum(course['required_count'] for course in course_results)
    completed_count = sum(course['completed_count'] for course in course_results)
    return {
        'class_key': class_key,
        'class_name': class_name,
        'term': term,
        'subjects': sorted(unique_subjects.values(), key=str.casefold),
        'course_results': course_results,
        'students': students,
        'grades': [
            grade
            for course in course_results
            for grade in course['grades']
        ],
        'required_count': required_count,
        'completed_count': completed_count,
        'missing_count': required_count - completed_count,
        'approved': bool(course_results) and all(
            course['approved'] for course in course_results
        ),
        'approval': next(
            (course['approval'] for course in course_results if course['approval']),
            None,
        ),
    }


def class_term_result_groups():
    class_terms = {}
    for class_key, timetable_model in TIMETABLES.items():
        for lesson in timetable_model.query.order_by(timetable_model.term).all():
            if normalize_class_name(lesson.classe) != class_key:
                continue
            class_terms.setdefault((class_key, lesson.term), lesson.classe)
    return [
        class_term_result_summary(class_key, term, class_name)
        for (class_key, term), class_name in sorted(
            class_terms.items(),
            key=lambda item: (item[1].casefold(), item[0][1].casefold()),
        )
    ]


def admin_required(view):
    @wraps(view)
    def decorated_view(*args, **kwargs):
        if 'admin_id' not in session:
            return redirect(url_for('schoolAdmin'))
        return view(*args, **kwargs)
    return decorated_view


def staff_required(view):
    @wraps(view)
    def decorated_view(*args, **kwargs):
        staff = db.session.get(Staff, session.get('staff_account_id'))
        if staff is None or not staff.is_active or not portal_is_enabled('staff'):
            session.pop('staff_account_id', None)
            return redirect(url_for('schoolAdmin'))
        g.staff_account = staff
        return view(*args, **kwargs)
    return decorated_view


def login_required(view):
    @wraps(view)
    def decorated_view(*args, **kwargs):
        if not portal_is_enabled('student'):
            session.pop('user_email', None)
            flash('The student portal is temporarily unavailable. Please contact the school office.', 'warning')
            return redirect(url_for('studentlogin'))
        if 'user_email' not in session:
            return redirect(url_for('studentlogin', next=request.url))
        return view(*args, **kwargs)
    return decorated_view


@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response    


@app.before_request
def enforce_student_portal_availability():
    if 'user_email' in session and not portal_is_enabled('student'):
        session.pop('user_email', None)
        flash('The student portal is temporarily unavailable. Please contact the school office.', 'warning')
        if request.endpoint != 'studentlogin':
            return redirect(url_for('studentlogin'))


@app.context_processor
def admin_navigation_context():
    page_by_endpoint = {
        'Adminpage': 'dashboard',
        'Adminlist': 'admissions',
        'student_management': 'students',
        'move_student_class': 'students',
        'move_students_class': 'students',
        'table1': 'timetable',
        'datatable': 'results',
        'fee_management': 'fees',
        'staff_results': 'staff_results',
        'staff_management': 'staff',
        'tasks': 'tasks',
    }
    return {'active_page': page_by_endpoint.get(request.endpoint, '')}


@app.route('/healthz', methods=['GET'])
def health_check():
    try:
        db.session.execute(db.text('SELECT 1'))
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception('Health check database query failed')
        return jsonify({'status': 'unavailable'}), 503
    return jsonify({'status': 'ok'})


# ... (your existing code)

@app.route('/',methods=['GET', 'POST'])
def index():
    success_message = request.args.get('success_message', '')
    return render_template('index.html', success_message=success_message)

@app.route('/index', methods=['GET', 'POST'])
def index1():
    if request.method == 'POST':
        
        
            return render_template('index.html')

    error_message = request.args.get('success_message', '')
    return render_template('index.html')


@app.route('/News', methods=['GET', 'POST'])
def News():
    if request.method == 'POST':
        
        
            return render_template('News.html')

    error_message = request.args.get('success_message', '')
    return render_template('News.html')
    

# ... (your existing code)

@app.route('/library', methods=['GET', 'POST'])
@login_required
def library():
    email = session.get('user_email', '')

    user_data = admitted.query.filter_by(email=email).first()
    if user_data is None:
        session.pop('user_email', None)
        return redirect(url_for('studentlogin'))
    resources = [
        resource
        for resource in LibraryResource.query.order_by(
            LibraryResource.uploaded_at.desc()
        ).all()
        if normalize_class_name(resource.class_name)
        == normalize_class_name(user_data.entry_class)
    ]
    return render_template(
        'library.html',
        student=user_data,
        resources=resources,
        today=date.today(),
    )


@app.route('/staff/library', methods=['GET', 'POST'])
@staff_required
def staff_library():
    if request.method == 'POST':
        course_title = (request.form.get('course_title') or '').strip()
        class_name = (request.form.get('class_name') or '').strip()
        description = (request.form.get('description') or '').strip()
        file = request.files.get('pdf')
        selected_class = next(
            (name for name in SCHOOL_CLASSES if name.casefold() == class_name.casefold()),
            None,
        )

        if (
            not course_title
            or len(course_title) > 120
            or selected_class is None
            or len(description) > 1000
        ):
            flash('Enter a course title, select a valid class, and keep the note under 1000 characters.', 'error')
            return redirect(url_for('staff_library'))
        if file is None or not file.filename:
            flash('Choose a PDF file to upload.', 'error')
            return redirect(url_for('staff_library'))
        if not file.filename.lower().endswith('.pdf'):
            flash('Only PDF files can be uploaded to the e-library.', 'error')
            return redirect(url_for('staff_library'))

        signature = file.stream.read(5)
        file.stream.seek(0)
        if signature != b'%PDF-':
            flash('The selected file is not a valid PDF document.', 'error')
            return redirect(url_for('staff_library'))

        filename = f'{uuid.uuid4().hex}.pdf'
        library_folder = app.config['LIBRARY_UPLOAD_FOLDER']
        file_path = os.path.join(library_folder, filename)
        try:
            os.makedirs(library_folder, exist_ok=True)
            file.save(file_path)
            resource = LibraryResource(
                staff_id=g.staff_account.id,
                class_name=selected_class,
                course_title=course_title,
                description=description or None,
                filename=filename,
            )
            db.session.add(resource)
            db.session.commit()
        except (OSError, SQLAlchemyError):
            db.session.rollback()
            app.logger.exception('Could not save e-library PDF')
            if os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    app.logger.exception('Could not remove incomplete e-library PDF %s', filename)
            flash('The PDF could not be uploaded. Please try again.', 'error')
            return redirect(url_for('staff_library'))

        flash(f'{course_title} uploaded for {selected_class}.', 'success')
        return redirect(url_for('staff_library'))

    resources = LibraryResource.query.filter_by(
        staff_id=g.staff_account.id
    ).order_by(LibraryResource.uploaded_at.desc()).all()
    return render_template(
        'staff_library.html',
        staff=g.staff_account,
        classes=SCHOOL_CLASSES,
        resources=resources,
    )


@app.route('/library/<int:resource_id>/download', methods=['GET'])
def download_library_resource(resource_id):
    resource = db.session.get(LibraryResource, resource_id)
    if resource is None:
        return '', 404

    if 'user_email' in session:
        student = admitted.query.filter_by(email=session['user_email']).first()
        if student is None:
            session.pop('user_email', None)
            return redirect(url_for('studentlogin'))
        if normalize_class_name(resource.class_name) != normalize_class_name(student.entry_class):
            return '', 404
    elif 'staff_account_id' in session:
        staff = db.session.get(Staff, session.get('staff_account_id'))
        if staff is None or not staff.is_active or not portal_is_enabled('staff'):
            session.pop('staff_account_id', None)
            return redirect(url_for('schoolAdmin'))
        if resource.staff_id != staff.id:
            return '', 404
    else:
        return redirect(url_for('studentlogin', next=request.url))

    response = send_from_directory(
        app.config['LIBRARY_UPLOAD_FOLDER'],
        resource.filename,
        as_attachment=False,
        download_name=f'{secure_filename(resource.course_title)}.pdf',
    )
    response.headers['Content-Disposition'] = (
        f'inline; filename="{secure_filename(resource.course_title)}.pdf"'
    )
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response
@app.route('/schoolAdmin', methods=['GET', 'POST'])
def schoolAdmin():
    error_message = None
    
    if request.method == 'POST':
        admin_id = (request.form.get('admin_id') or '').strip()
        password = request.form.get('password') or ''

        if (
            admin_id == app.config['ADMIN_ID']
            and hmac.compare_digest(password, app.config['ADMIN_PASSWORD'])
        ):
            session.clear()
            session['admin_id'] = admin_id
            return redirect(url_for('Adminpage'))

        staff = Staff.query.filter_by(staff_id=admin_id, is_active=True).first()
        if not portal_is_enabled('staff'):
            error_message = 'The staff portal is temporarily unavailable. Please contact the school administrator.'
        elif staff and bcrypt.check_password_hash(staff.password_hash, password):
            session.clear()
            session['staff_account_id'] = staff.id
            return redirect(url_for('tasks'))
        else:
            error_message = 'Invalid staff ID or password. Please try again.'

    return render_template(
        'schoolAdmin.html',
        error_message=error_message,
        staff_portal_enabled=portal_is_enabled('staff'),
    )

    
RESULTS_FOLDER = os.environ.get(
    'RESULTS_FOLDER',
    os.path.join(app.root_path, 'results'),
)

os.makedirs(RESULTS_FOLDER, exist_ok=True)

@app.route('/Adminpage', methods=['GET', 'POST'])
@admin_required
def Adminpage():
    total_files = CourseGrade.query.count()
    pending_applications = portal.query.filter(
        ~db.func.lower(portal.email).in_(
            db.session.query(db.func.lower(admitted.email))
        )
    ).count()
    result_groups = class_term_result_groups()
    pending_results = [group for group in result_groups if not group['approved']]
    ready_results_count = sum(
        group['missing_count'] == 0 and group['required_count'] > 0
        for group in pending_results
    )
    return render_template(
        'Adminpage.html',
        total_files=total_files,
        total_students=pending_applications,
        admitted_students=admitted.query.count(),
        active_staff=Staff.query.filter_by(is_active=True).count(),
        pending_results=pending_results,
        ready_results_count=ready_results_count,
    )


@app.route('/students', methods=['GET'])
@admin_required
def student_management():
    students = admitted.query.order_by(
        admitted.entry_class, admitted.firstName, admitted.lastName
    ).all()
    current_classes = sorted(
        set(SCHOOL_CLASSES) | {student.entry_class for student in students},
        key=str.casefold,
    )
    graduatable_students = sum(
        normalize_class_name(student.entry_class) in {
            'sss3', 'grade12a', 'grade12b',
        }
        and not student.is_graduated
        for student in students
    )
    return render_template(
        'students.html',
        students=students,
        graduatable_students=graduatable_students,
        classes=SCHOOL_CLASSES,
        current_classes=current_classes,
        student_class_keys={
            student.id: normalize_class_name(student.entry_class)
            for student in students
        },
    )


@app.route('/students/<int:student_id>/class', methods=['POST'])
@admin_required
def move_student_class(student_id):
    student = db.session.get(admitted, student_id)
    if student is None:
        return '', 404
    if student.is_graduated:
        flash('Graduated students cannot be moved to another class.', 'error')
        return redirect(url_for('student_management'))

    target_class = (request.form.get('entry_class') or '').strip()
    target_class_option = next(
        (class_name for class_name in SCHOOL_CLASSES
         if class_name.casefold() == target_class.casefold()),
        None,
    )
    if target_class_option is None:
        flash('Choose a valid destination class.', 'error')
        return redirect(url_for('student_management'))
    if normalize_class_name(target_class_option) == normalize_class_name(student.entry_class):
        flash(f'{student.firstName} is already enrolled in {target_class_option}.', 'error')
        return redirect(url_for('student_management'))

    previous_class = student.entry_class
    student.entry_class = target_class_option
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception('Could not move student to another class')
        flash('The student could not be moved. Please try again.', 'error')
    else:
        try:
            issued_invoices = ensure_student_class_invoices(student)
        except SQLAlchemyError:
            flash(
                f'{student.firstName} moved to {target_class_option}, but class invoices could not be prepared. '
                'They will be retried when the student opens Fees & invoices.',
                'warning',
            )
        else:
            suffix = (
                f' {len(issued_invoices)} invoice(s) added to the student portal.'
                if issued_invoices else ''
            )
            flash(
                f'{student.firstName} {student.lastName} moved from {previous_class} to '
                f'{target_class_option}.{suffix}',
                'success',
            )
    return redirect(url_for('student_management'))


@app.route('/students/move-class', methods=['POST'])
@admin_required
def move_students_class():
    source_class = (request.form.get('source_class') or '').strip()
    target_class = (request.form.get('entry_class') or '').strip()
    student_ids = request.form.getlist('student_ids')
    existing_classes = {
        student.entry_class for student in admitted.query.with_entities(
            admitted.entry_class
        ).distinct().all()
    }
    selectable_source_classes = set(SCHOOL_CLASSES) | existing_classes
    source_class_option = next(
        (class_name for class_name in selectable_source_classes
         if class_name.casefold() == source_class.casefold()),
        None,
    )
    target_class_option = next(
        (class_name for class_name in SCHOOL_CLASSES
         if class_name.casefold() == target_class.casefold()),
        None,
    )
    if source_class_option is None or target_class_option is None:
        flash('Choose valid current and destination classes.', 'error')
        return redirect(url_for('student_management'))
    if normalize_class_name(source_class_option) == normalize_class_name(target_class_option):
        flash('Choose a different destination class.', 'error')
        return redirect(url_for('student_management'))

    try:
        selected_ids = {int(student_id) for student_id in student_ids}
    except ValueError:
        flash('Select valid students to move.', 'error')
        return redirect(url_for('student_management'))
    if not selected_ids:
        flash('Select at least one student to move.', 'error')
        return redirect(url_for('student_management'))

    students = admitted.query.filter(admitted.id.in_(selected_ids)).all()
    if (
        len(students) != len(selected_ids)
        or any(
            normalize_class_name(student.entry_class)
            != normalize_class_name(source_class_option)
            or student.is_graduated
            for student in students
        )
    ):
        flash('Some selected students are no longer in the chosen current class. Refresh and try again.', 'error')
        return redirect(url_for('student_management'))

    for student in students:
        student.entry_class = target_class_option
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception('Could not bulk move students to another class')
        flash('The selected students could not be moved. Please try again.', 'error')
    else:
        invoice_failure_count = 0
        issued_invoice_count = 0
        for student in students:
            try:
                issued_invoice_count += len(ensure_student_class_invoices(student))
            except SQLAlchemyError:
                invoice_failure_count += 1
                app.logger.exception(
                    'Could not prepare class invoices after moving student %s',
                    student.id,
                )
        move_message = (
            f'{len(students)} student{"s" if len(students) != 1 else ""} moved from '
            f'{source_class_option} to {target_class_option}.'
        )
        if invoice_failure_count:
            flash(
                f'{move_message} Invoices could not be prepared for {invoice_failure_count} student(s); '
                'they will be retried when the students open Fees & invoices.',
                'warning',
            )
        else:
            if issued_invoice_count:
                move_message += f' {issued_invoice_count} invoice(s) added to student portals.'
            flash(move_message, 'success')
    return redirect(url_for('student_management'))


@app.route('/students/graduate-sss3', methods=['POST'])
@admin_required
def graduate_sss3_students():
    students = admitted.query.filter_by(is_graduated=False).all()
    graduating_students = [
        student for student in students
        if normalize_class_name(student.entry_class) in {
            'sss3', 'grade12a', 'grade12b',
        }
    ]
    if not graduating_students:
        flash('There are no active Grade 12 or legacy SSS 3 students to graduate.', 'warning')
        return redirect(url_for('student_management'))

    for student in graduating_students:
        student.is_graduated = True
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception('Could not graduate final-year students')
        flash('The final-year students could not be graduated. Please try again.', 'error')
    else:
        flash(
            f'{len(graduating_students)} final-year student'
            f'{"s" if len(graduating_students) != 1 else ""} marked as graduated. '
            'Their records and read-only portal access have been retained.',
            'success',
        )
    return redirect(url_for('student_management'))


@app.route('/datatable', methods=['GET'])
@admin_required
def datatable():
    all_groups = class_term_result_groups()
    class_filter = (request.args.get('class') or '').strip().lower()
    if class_filter not in TIMETABLES:
        class_filter = ''
    result_classes = {}
    for group in all_groups:
        result_classes.setdefault(group['class_key'], group['class_name'])
    if class_filter:
        all_groups = [
            group for group in all_groups
            if group['class_key'] == class_filter
        ]
    view = request.args.get('view', 'pending')
    if view not in {'pending', 'approved'}:
        view = 'pending'
    result_groups = []
    for group in all_groups:
        visible_courses = [
            course for course in group['course_results']
            if course['approved'] == (view == 'approved')
        ]
        if not visible_courses:
            continue
        result_groups.append({
            **group,
            'course_results': visible_courses,
            'subjects': [course['subject'] for course in visible_courses],
            'completed_count': sum(
                course['completed_count'] for course in visible_courses
            ),
            'required_count': sum(
                course['required_count'] for course in visible_courses
            ),
            'missing_count': sum(
                course['missing_count'] for course in visible_courses
            ),
            'approved': view == 'approved',
            'approval': max(
                (course['approval'] for course in visible_courses),
                key=lambda approval: approval.approved_at,
            ) if view == 'approved' else None,
        })
    return render_template(
        'datatable.html',
        result_groups=result_groups,
        pending_count=sum(
            not course['approved']
            for group in all_groups
            for course in group['course_results']
        ),
        approved_count=sum(
            course['approved']
            for group in all_groups
            for course in group['course_results']
        ),
        current_view=view,
        class_filter=class_filter,
        result_classes=result_classes,
    )


@app.route('/results/approve', methods=['POST'])
@admin_required
def approve_class_results():
    class_key = (request.form.get('timetable_class') or '').strip().lower()
    term = (request.form.get('term') or '').strip()
    subject = (request.form.get('subject') or '').strip()
    timetable_model = TIMETABLES.get(class_key)
    if timetable_model is None or not term or not subject:
        flash('Choose a valid class, term, and subject to approve.', 'error')
        return redirect(url_for('datatable'))

    lessons = timetable_model.query.filter_by(term=term).all()
    class_name = next(
        (
            lesson.classe for lesson in lessons
            if normalize_class_name(lesson.classe) == class_key
        ),
        None,
    )
    if class_name is None:
        flash('No scheduled courses were found for that class and term.', 'error')
        return redirect(url_for('datatable'))

    scheduled_subject = next(
        (
            lesson.subject for lesson in lessons
            if normalize_class_name(lesson.classe) == class_key
            and lesson.subject.casefold() == subject.casefold()
        ),
        None,
    )
    if scheduled_subject is None:
        flash('That subject is not scheduled for the selected class and term.', 'error')
        return redirect(url_for('datatable'))

    students = result_roster(class_name)
    grades = class_course_grades(class_key, term, scheduled_subject, students)
    complete_student_ids = {
        grade.student_id
        for grade in grades
        if result_grade_for_total(grade.total_score)
        and any(score is not None for score in (
            grade.ca1_score,
            grade.ca2_score,
            grade.ca3_score,
        ))
        and grade.exam_score is not None
    }
    missing_count = len(students) - len(complete_student_ids)
    if not students or missing_count:
        flash(
            f"Results for {scheduled_subject} are incomplete: {missing_count} student entries still need at least one CA and an exam score.",
            'error',
        )
        return redirect(url_for('datatable'))

    approval = CourseResultApproval.query.filter_by(
        timetable_class=class_key,
        term=term,
        subject=scheduled_subject,
    ).first()
    if approval is None:
        approval = CourseResultApproval(
            timetable_class=class_key,
            class_name=class_name,
            term=term,
            subject=scheduled_subject,
            approved_by=session['admin_id'],
        )
    approval.class_name = class_name
    approval.approved_by = session['admin_id']
    approval.approved_at = datetime.now()
    db.session.add(approval)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception('Could not approve class results')
        flash('Course results could not be approved. Please try again.', 'error')
    else:
        flash(
            f"{scheduled_subject} results for {class_name}, {term}, are approved and visible to students.",
            'success',
        )
    return redirect(url_for('datatable'))


@app.route('/fees', methods=['GET', 'POST'])
@admin_required
def fee_management():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'save_schedule':
            class_name = (request.form.get('class_name') or '').strip()
            fee_type = (request.form.get('fee_type') or '').strip()
            amount = parse_fee_amount(request.form.get('amount'))
            enrolled_class = admitted.query.filter_by(entry_class=class_name).first()
            if not enrolled_class or not fee_type or len(fee_type) > 120 or amount is None:
                flash('Choose a class with enrolled students, enter a fee name, and provide a valid amount.', 'error')
                return redirect(url_for('fee_management'))

            schedule = FeeSchedule.query.filter_by(
                class_name=class_name,
                fee_type=fee_type,
            ).first()
            if schedule is None:
                schedule = FeeSchedule(class_name=class_name, fee_type=fee_type, amount=amount)
                db.session.add(schedule)
            else:
                schedule.amount = amount
            try:
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                app.logger.exception('Could not save class fee schedule')
                flash('The class fee could not be saved. Please try again.', 'error')
            else:
                flash(f'{fee_type} fee for {class_name} saved.', 'success')
            return redirect(url_for('fee_management'))

        if action == 'update_schedule':
            schedule_id = request.form.get('schedule_id', type=int)
            schedule = db.session.get(FeeSchedule, schedule_id) if schedule_id else None
            fee_type = (request.form.get('fee_type') or '').strip()
            amount = parse_fee_amount(request.form.get('amount'))
            if schedule is None:
                flash('That class fee rate could not be found.', 'error')
            elif not fee_type or len(fee_type) > 120 or amount is None:
                flash('Enter a fee name and a valid positive amount.', 'error')
            else:
                schedule.fee_type = fee_type
                schedule.amount = amount
                try:
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    flash('That class already has a rate with this fee name.', 'error')
                except SQLAlchemyError:
                    db.session.rollback()
                    app.logger.exception('Could not update class fee schedule %s', schedule_id)
                    flash('The class fee rate could not be updated. Please try again.', 'error')
                else:
                    flash(f'{fee_type} rate for {schedule.class_name} updated.', 'success')
            return redirect(url_for('fee_management'))

        if action == 'delete_schedule':
            schedule_id = request.form.get('schedule_id', type=int)
            schedule = db.session.get(FeeSchedule, schedule_id) if schedule_id else None
            if schedule is None:
                flash('That class fee rate could not be found.', 'error')
            else:
                class_name, fee_type = schedule.class_name, schedule.fee_type
                try:
                    db.session.delete(schedule)
                    db.session.commit()
                except SQLAlchemyError:
                    db.session.rollback()
                    app.logger.exception('Could not delete class fee schedule %s', schedule_id)
                    flash('The class fee rate could not be deleted. Please try again.', 'error')
                else:
                    flash(
                        f'{fee_type} rate for {class_name} deleted. Previously issued invoices are unchanged.',
                        'success',
                    )
            return redirect(url_for('fee_management'))

        if action in ('issue_invoice', 'issue_class_invoices'):
            student_id = request.form.get('student_id', type=int)
            class_name = (request.form.get('class_name') or '').strip()
            schedule_id = request.form.get('schedule_id', type=int)
            due_date_value = (request.form.get('due_date') or '').strip()
            description = (request.form.get('description') or '').strip()
            schedule = db.session.get(FeeSchedule, schedule_id) if schedule_id else None

            try:
                due_date = date.fromisoformat(due_date_value) if due_date_value else None
            except ValueError:
                due_date = None
                if due_date_value:
                    flash('Enter a valid invoice due date.', 'error')
                    return redirect(url_for('fee_management'))

            if schedule is None or len(description) > 1000:
                flash('Choose a valid fee rate and keep the invoice note under 1000 characters.', 'error')
                return redirect(url_for('fee_management'))

            if action == 'issue_invoice':
                student = db.session.get(admitted, student_id) if student_id else None
                if (
                    student is None
                    or schedule.class_name.casefold() != student.entry_class.strip().casefold()
                ):
                    flash('Choose a student and a fee rate configured for that student’s class.', 'error')
                    return redirect(url_for('fee_management'))
                students_to_invoice = [student]
            else:
                if (
                    normalize_class_name(schedule.class_name)
                    != normalize_class_name(class_name)
                ):
                    flash('Choose a fee rate configured for the selected class.', 'error')
                    return redirect(url_for('fee_management'))
                students_to_invoice = [
                    student
                    for student in admitted.query.all()
                    if normalize_class_name(student.entry_class)
                    == normalize_class_name(class_name)
                ]
                if not students_to_invoice:
                    flash('There are no admitted students in the selected class.', 'error')
                    return redirect(url_for('fee_management'))

            invoice_batch_id = (
                str(uuid.uuid4()) if action == 'issue_class_invoices' else None
            )
            issued_invoices = [
                FeeInvoice(
                    student_id=student.id,
                    fee_type=schedule.fee_type,
                    description=description or None,
                    class_name=student.entry_class,
                    school_session=student.entry_session,
                    amount=schedule.amount,
                    due_date=due_date,
                    invoice_batch_id=invoice_batch_id,
                )
                for student in students_to_invoice
            ]
            db.session.add_all(issued_invoices)
            try:
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                app.logger.exception('Could not issue fee invoice(s)')
                flash('The invoice(s) could not be issued. Please try again.', 'error')
            else:
                emailed_count = sum(email_fee_invoice(invoice) for invoice in issued_invoices)
                failed_email_count = len(issued_invoices) - emailed_count
                if action == 'issue_invoice':
                    issued_message = (
                        f'{schedule.fee_type} invoice issued to '
                        f'{students_to_invoice[0].firstName} {students_to_invoice[0].lastName}.'
                    )
                else:
                    issued_message = (
                        f'{schedule.fee_type} invoice issued to all '
                        f'{len(students_to_invoice)} students in {class_name}.'
                    )
                if failed_email_count:
                    flash(
                        f'{issued_message} Emailed {emailed_count} of {len(issued_invoices)} students; '
                        f'{failed_email_count} email(s) could not be sent. You can retry from the invoice list.',
                        'warning',
                    )
                else:
                    flash(
                        f'{issued_message} Fee notice emailed to '
                        f'{emailed_count} student(s).',
                        'success',
                    )
            return redirect(url_for('fee_management'))

        if action == 'update_invoice':
            invoice_id = request.form.get('invoice_id', type=int)
            invoice = db.session.get(FeeInvoice, invoice_id) if invoice_id else None
            fee_type = (request.form.get('fee_type') or '').strip()
            amount = parse_fee_amount(request.form.get('amount'))
            description = (request.form.get('description') or '').strip()
            due_date_value = (request.form.get('due_date') or '').strip()
            try:
                due_date = date.fromisoformat(due_date_value) if due_date_value else None
            except ValueError:
                flash('Enter a valid invoice due date.', 'error')
                return redirect(url_for('fee_management'))

            if invoice is None:
                flash('That invoice could not be found.', 'error')
                return redirect(url_for('fee_management'))
            if not fee_type or len(fee_type) > 120 or amount is None:
                flash('Enter a fee name and a valid positive amount.', 'error')
                return redirect(url_for('fee_management'))
            if len(description) > 1000:
                flash('Keep the invoice note under 1000 characters.', 'error')
                return redirect(url_for('fee_management'))

            invoices_to_update = (
                FeeInvoice.query.filter_by(
                    invoice_batch_id=invoice.invoice_batch_id
                ).all()
                if invoice.invoice_batch_id
                else [invoice]
            )
            for batch_invoice in invoices_to_update:
                batch_invoice.fee_type = fee_type
                batch_invoice.amount = amount
                batch_invoice.description = description or None
                batch_invoice.due_date = due_date
            try:
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                app.logger.exception('Could not update fee invoice %s', invoice_id)
                flash('The invoice could not be updated. Please try again.', 'error')
            else:
                flash(f'Invoice #{invoice.id} updated.', 'success')
            return redirect(url_for('fee_management'))

        if action == 'share_invoice':
            invoice_id = request.form.get('invoice_id', type=int)
            invoice = db.session.get(FeeInvoice, invoice_id) if invoice_id else None
            if invoice is None:
                flash('That invoice could not be found.', 'error')
            elif invoice.invoice_batch_id:
                flash(f'Invoice #{invoice.id} is already shared with its class.', 'warning')
            else:
                invoice.invoice_batch_id = str(uuid.uuid4())
                try:
                    db.session.commit()
                except SQLAlchemyError:
                    db.session.rollback()
                    app.logger.exception('Could not share fee invoice %s with its class', invoice_id)
                    flash('The invoice could not be shared with its class. Please try again.', 'error')
                else:
                    flash(
                        f'Invoice #{invoice.id} will also appear for future students in '
                        f'{invoice.class_name} for {invoice.school_session}.',
                        'success',
                    )
            return redirect(url_for('fee_management'))

        if action == 'email_invoice':
            invoice_id = request.form.get('invoice_id', type=int)
            invoice = db.session.get(FeeInvoice, invoice_id) if invoice_id else None
            if invoice is None:
                flash('That invoice could not be found.', 'error')
            elif email_fee_invoice(invoice):
                flash(f'Fee notice for invoice #{invoice.id} emailed to {invoice.student.email}.', 'success')
            else:
                flash(
                    'The invoice is still saved, but its email could not be sent. '
                    'Check the student email address and mail settings, then try again.',
                    'error',
                )
            return redirect(url_for('fee_management'))

        flash('Choose a valid fee action.', 'error')
        return redirect(url_for('fee_management'))

    students = admitted.query.order_by(admitted.entry_class, admitted.firstName, admitted.lastName).all()
    schedules = FeeSchedule.query.order_by(FeeSchedule.class_name, FeeSchedule.fee_type).all()
    invoices = FeeInvoice.query.order_by(FeeInvoice.issued_at.desc()).all()
    classes = sorted(
        set(SCHOOL_CLASSES) | {student.entry_class for student in students},
        key=str.casefold,
    )
    return render_template(
        'fees.html',
        students=students,
        schedules=schedules,
        invoices=invoices,
        classes=classes,
    )


@app.route('/staff/results', methods=['GET'])
@staff_required
def staff_results():
    courses = assigned_result_courses(g.staff_account)
    selected_class = (request.args.get('class') or '').strip().lower()
    selected_term = (request.args.get('term') or '').strip()
    selected_subject = (request.args.get('subject') or '').strip()
    available_classes = {}
    for course in courses:
        available_classes.setdefault(course['class_key'], course['class_name'])
    available_classes = [
        {'key': class_key, 'name': class_name}
        for class_key, class_name in sorted(available_classes.items())
    ]
    selected_course = next(
        (
            course for course in courses
            if course['class_key'] == selected_class
            and course['term'].casefold() == selected_term.casefold()
            and course['subject'].casefold() == selected_subject.casefold()
        ),
        None,
    )
    students = []
    grades_by_student = {}
    approval = None
    course_complete = False
    if selected_course:
        students = result_roster(selected_course['class_name'])
        grade_records = CourseGrade.query.filter_by(
            timetable_class=selected_course['class_key'],
            term=selected_course['term'],
            subject=selected_course['subject'],
        ).all()
        grades_by_student = {grade.student_id: grade for grade in grade_records}
        approval = CourseResultApproval.query.filter_by(
            timetable_class=selected_course['class_key'],
            term=selected_course['term'],
            subject=selected_course['subject'],
        ).first()
        course_complete = bool(students) and all(
            (grade := grades_by_student.get(student.id)) is not None
            and grade.exam_score is not None
            and any(score is not None for score in (
                grade.ca1_score,
                grade.ca2_score,
                grade.ca3_score,
            ))
            for student in students
        )

    return render_template(
        'staff_results.html',
        courses=courses,
        available_classes=available_classes,
        selected_course=selected_course,
        students=students,
        grades_by_student=grades_by_student,
        result_approved=approval is not None,
        course_complete=course_complete,
        staff=g.staff_account,
    )


@app.route(
    '/staff/results/<class_name>/<int:timetable_id>',
    methods=['POST'],
)
@staff_required
def save_course_results(class_name, timetable_id):
    timetable_model = TIMETABLES.get(class_name.lower())
    if timetable_model is None:
        return '', 404

    lesson = timetable_model.query.filter_by(
        id=timetable_id,
        techername=g.staff_account.full_name,
    ).first_or_404()
    class_key = class_name.lower()
    if CourseResultApproval.query.filter_by(
        timetable_class=class_key,
        term=lesson.term,
        subject=lesson.subject,
    ).first():
        flash(
            f'{lesson.subject} results for {lesson.classe} have been approved and can no longer be changed.',
            'error',
        )
        return redirect(url_for(
            'staff_results',
            **{'class': class_key, 'term': lesson.term, 'subject': lesson.subject},
        ))

    students = result_roster(lesson.classe)
    score_updates = []
    grade_records = CourseGrade.query.filter_by(
        timetable_class=class_key,
        term=lesson.term,
        subject=lesson.subject,
    ).all()
    grades_by_student = {grade.student_id: grade for grade in grade_records}
    score_fields = ('ca1_score', 'ca2_score', 'ca3_score', 'exam_score')
    for student in students:
        existing_grade = grades_by_student.get(student.id)
        values = {}
        for field in score_fields:
            raw_score = (request.form.get(f'{field}_{student.id}') or '').strip()
            if raw_score:
                score = parse_assessment_score(raw_score)
                if score is None:
                    flash('Marks must be valid non-negative numbers.', 'error')
                    return redirect(url_for(
                        'staff_results',
                        **{'class': class_key, 'term': lesson.term, 'subject': lesson.subject},
                    ))
                values[field] = score
            else:
                values[field] = getattr(existing_grade, field) if existing_grade else None

        if values['exam_score'] is None or not any(
            values[field] is not None for field in score_fields[:3]
        ):
            flash(
                f'Complete the exam mark and at least one CA mark for every student in {lesson.classe} before submitting.',
                'error',
            )
            return redirect(url_for(
                'staff_results',
                **{'class': class_key, 'term': lesson.term, 'subject': lesson.subject},
            ))
        score_updates.append((student, values))

    if not students:
        flash('There are no admitted students in this class to submit results for.', 'error')
        return redirect(url_for(
            'staff_results',
            **{'class': class_key, 'term': lesson.term, 'subject': lesson.subject},
        ))

    try:
        for student, values in score_updates:
            grade = grades_by_student.get(student.id)
            if grade is None:
                grade = CourseGrade(
                    student_id=student.id,
                    staff_id=g.staff_account.id,
                    timetable_class=class_key,
                    class_name=lesson.classe,
                    term=lesson.term,
                    subject=lesson.subject,
                )
                db.session.add(grade)
            grade.staff_id = g.staff_account.id
            grade.class_name = lesson.classe
            for field, score in values.items():
                setattr(grade, field, score)
            grade.grade = result_grade_for_total(grade.total_score)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception('Could not save course marks')
        flash('The course marks could not be saved. Please try again.', 'error')
    else:
        flash(
            f'{lesson.subject} results submitted for all {len(score_updates)} students in {lesson.classe}. The administrator can now review and approve the class results.',
            'success',
        )
    return redirect(url_for(
        'staff_results',
        **{'class': class_key, 'term': lesson.term, 'subject': lesson.subject},
    ))


@app.route('/staff-management', methods=['GET', 'POST'])
@admin_required
def staff_management():
    if request.method == 'POST':
        action = (request.form.get('action') or '').strip()
        if action == 'update_staff':
            staff_pk = request.form.get('staff_pk', type=int)
            staff = db.session.get(Staff, staff_pk) if staff_pk else None
            staff_id = (request.form.get('staff_id') or '').strip()
            full_name = (request.form.get('full_name') or '').strip()
            email = (request.form.get('email') or '').strip().lower()
            password = request.form.get('password') or ''
            is_active = request.form.get('is_active') == 'enabled'

            if staff is None:
                flash('That staff account could not be found.', 'error')
            elif (
                not staff_id or len(staff_id) > 50
                or not full_name or len(full_name) > 120
                or not email or len(email) > 120 or '@' not in email
            ):
                flash('Enter a valid staff ID, full name, and email address.', 'error')
            elif password and len(password) < 8:
                flash('A new staff password must be at least 8 characters long.', 'error')
            elif Staff.query.filter(
                Staff.id != staff.id,
                db.or_(
                    Staff.staff_id == staff_id,
                    db.func.lower(Staff.email) == email,
                ),
            ).first():
                flash('That staff ID or email address is already in use.', 'error')
            elif Staff.query.filter(
                Staff.id != staff.id,
                db.func.lower(Staff.full_name) == full_name.casefold(),
            ).first():
                flash(
                    'Staff full names must be unique because timetable assignments identify teachers by name.',
                    'error',
                )
            elif (
                staff.full_name.casefold() != full_name.casefold()
                and Staff.query.filter(
                    Staff.id != staff.id,
                    db.func.lower(Staff.full_name) == staff.full_name.casefold(),
                ).first()
            ):
                flash(
                    'This staff member shares a name with another account, so their existing course assignments cannot be safely renamed.',
                    'error',
                )
            else:
                previous_name = staff.full_name
                staff.staff_id = staff_id
                staff.full_name = full_name
                staff.email = email
                staff.is_active = is_active
                if password:
                    staff.password_hash = hash_password(password)
                if previous_name != full_name:
                    for timetable_model in TIMETABLES.values():
                        timetable_model.query.filter_by(
                            techername=previous_name
                        ).update(
                            {timetable_model.techername: full_name},
                            synchronize_session=False,
                        )
                try:
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    flash('That staff ID or email address is already in use.', 'error')
                except SQLAlchemyError:
                    db.session.rollback()
                    app.logger.exception('Could not update staff account %s', staff_pk)
                    flash('The staff account could not be updated. Please try again.', 'error')
                else:
                    flash(f'Staff account for {full_name} updated.', 'success')
            return redirect(url_for('staff_management'))

        if action == 'change_assignment':
            staff_pk = request.form.get('staff_pk', type=int)
            staff = db.session.get(Staff, staff_pk) if staff_pk else None
            class_key = (request.form.get('class_key') or '').strip()
            lesson_id = request.form.get('lesson_id', type=int)
            target_staff_pk = request.form.get('target_staff_id', type=int)
            target_staff = db.session.get(Staff, target_staff_pk) if target_staff_pk else None
            timetable_model = TIMETABLES.get(class_key)
            lesson = (
                db.session.get(timetable_model, lesson_id)
                if timetable_model and lesson_id else None
            )
            if (
                staff is None or target_staff is None or not target_staff.is_active
                or lesson is None
                or lesson.techername != staff.full_name
                or normalize_class_name(lesson.classe) != class_key
            ):
                flash('That course assignment could not be verified. Refresh and try again.', 'error')
            elif target_staff.id == staff.id:
                flash(f'{lesson.subject} is already assigned to {staff.full_name}.', 'warning')
            elif target_staff.full_name.casefold() == staff.full_name.casefold():
                flash(
                    'The selected accounts share the same name, so the timetable assignment cannot distinguish them.',
                    'error',
                )
            else:
                lesson.techername = target_staff.full_name
                try:
                    db.session.commit()
                except SQLAlchemyError:
                    db.session.rollback()
                    app.logger.exception(
                        'Could not change teacher for timetable lesson %s in %s',
                        lesson_id,
                        class_key,
                    )
                    flash('The course assignment could not be changed. Please try again.', 'error')
                else:
                    flash(
                        f'{lesson.subject} ({lesson.classe}, {lesson.term}) is now assigned to '
                        f'{target_staff.full_name}.',
                        'success',
                    )
            return redirect(url_for('staff_management'))

        if action:
            flash('Choose a valid staff-management action.', 'error')
            return redirect(url_for('staff_management'))

        staff_id = (request.form.get('staff_id') or '').strip()
        full_name = (request.form.get('full_name') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''

        if not staff_id or not full_name or not email or not password:
            flash('Complete every field to create a staff account.', 'error')
        elif len(password) < 8:
            flash('Staff passwords must be at least 8 characters long.', 'error')
        elif Staff.query.filter(
            (Staff.staff_id == staff_id) | (Staff.email == email)
        ).first():
            flash('That staff ID or email address is already in use.', 'error')
        elif Staff.query.filter(
            db.func.lower(Staff.full_name) == full_name.casefold()
        ).first():
            flash(
                'Staff full names must be unique because timetable assignments identify teachers by name.',
                'error',
            )
        else:
            staff = Staff(
                staff_id=staff_id,
                full_name=full_name,
                email=email,
                password_hash=hash_password(password),
            )
            db.session.add(staff)
            try:
                db.session.commit()
                mail_sent = send_email(
                    email,
                    'Welcome to Florence Court',
                    (
                        f'Hello {full_name},\n\n'
                        'Your staff portal account has been created.\n'
                        f'Sign in with staff ID: {staff_id}\n'
                        f'Temporary password: {password}\n\n'
                        'Please keep your login details private.'
                    ),
                )
                if mail_sent:
                    flash(f'Account created for {full_name}; welcome email sent.', 'success')
                else:
                    flash(
                        f'Account created for {full_name}, but the welcome email could not be sent. Check the mail settings and logs.',
                        'warning',
                    )
                return redirect(url_for('staff_management'))
            except IntegrityError:
                db.session.rollback()
                flash('That staff ID or email address is already in use.', 'error')

    staff_members = Staff.query.order_by(Staff.full_name).all()
    staff_course_assignments = {
        member.id: assigned_result_courses(member)
        for member in staff_members
    }
    return render_template(
        'staff_management.html',
        staff_members=staff_members,
        staff_course_assignments=staff_course_assignments,
        student_portal_enabled=portal_is_enabled('student'),
        staff_portal_enabled=portal_is_enabled('staff'),
        timetable_classes=TIMETABLE_CLASS_NAMES,
    )


@app.route('/admin/courses', methods=['GET', 'POST'])
@admin_required
def course_management():
    class_names = TIMETABLE_CLASS_NAMES
    if request.method == 'POST':
        action = (request.form.get('action') or '').strip()
        if action == 'add':
            name = (request.form.get('name') or '').strip()
            if not name or len(name) > 100:
                flash('Enter a course name of 1 to 100 characters.', 'error')
            elif any(course.name.casefold() == name.casefold() for course in CourseCatalog.query.all()):
                flash('That course is already in the course list.', 'error')
            else:
                db.session.add(CourseCatalog(name=name))
                try:
                    db.session.commit()
                except SQLAlchemyError:
                    db.session.rollback()
                    app.logger.exception('Could not add course to the course catalog')
                    flash('The course could not be added. Please try again.', 'error')
                else:
                    flash(f'{name} was added to the course list.', 'success')
            return redirect(url_for('course_management'))

        if action == 'delete':
            course = db.session.get(CourseCatalog, request.form.get('course_id', type=int))
            if course is None:
                flash('The selected course could not be found.', 'error')
            else:
                linked_lessons = sum(
                    model.query.filter(
                        db.func.lower(model.subject) == course.name.casefold()
                    ).count()
                    for model in TIMETABLES.values()
                )
                if linked_lessons:
                    flash(
                        f'{course.name} is already used in {linked_lessons} timetable lesson(s) and cannot be removed.',
                        'error',
                    )
                else:
                    db.session.delete(course)
                    try:
                        db.session.commit()
                    except SQLAlchemyError:
                        db.session.rollback()
                        app.logger.exception('Could not remove course from the course catalog')
                        flash('The course could not be removed. Please try again.', 'error')
                    else:
                        flash(f'{course.name} was removed from the course list.', 'success')
            return redirect(url_for('course_management'))

        if action == 'assign':
            teacher = (request.form.get('teacher') or '').strip()
            term = (request.form.get('term') or '').strip().lower()
            course_ids = request.form.getlist('course_id[]')
            classes = request.form.getlist('classe[]')
            lesson_dates = request.form.getlist('date[]')
            lesson_times = request.form.getlist('time[]')
            active_staff_names = {
                staff.full_name for staff in Staff.query.filter_by(is_active=True).all()
            }
            rows = list(zip(course_ids, classes, lesson_dates, lesson_times))
            if (
                teacher not in active_staff_names
                or term not in {'first', 'second', 'third'}
                or not rows
                or len(rows) != len(course_ids)
                or len(rows) != len(classes)
                or len(rows) != len(lesson_dates)
                or len(rows) != len(lesson_times)
                or any(
                    not course_id.isdigit()
                    or class_key not in TIMETABLE_CLASS_NAMES
                    or not lesson_date
                    or not lesson_time
                    for course_id, class_key, lesson_date, lesson_time in rows
                )
            ):
                flash('Choose an active teacher, a term, and complete valid course lesson rows.', 'error')
                return redirect(url_for('course_management'))

            courses = {
                course.id: course
                for course in CourseCatalog.query.filter(
                    CourseCatalog.id.in_({int(row[0]) for row in rows})
                ).all()
            }
            if len(courses) != len({int(row[0]) for row in rows}):
                flash('One or more selected courses no longer exist. Refresh and try again.', 'error')
                return redirect(url_for('course_management'))

            try:
                prepared_rows = [
                    (
                        courses[int(course_id)],
                        class_key,
                        date.fromisoformat(lesson_date),
                        datetime.strptime(lesson_time, '%H:%M').time(),
                    )
                    for course_id, class_key, lesson_date, lesson_time in rows
                ]
            except ValueError:
                flash('Enter a valid date and time for every lesson.', 'error')
                return redirect(url_for('course_management'))

            duplicate_rows = {
                (class_key, course.name.casefold())
                for course, class_key, _, _ in prepared_rows
                if sum(
                    1 for other_course, other_class, _, _ in prepared_rows
                    if other_class == class_key
                    and other_course.name.casefold() == course.name.casefold()
                ) > 1
            }
            if duplicate_rows:
                flash('A course can only appear once per class in this assignment. Remove duplicate rows.', 'error')
                return redirect(url_for('course_management'))

            try:
                for course, class_key, lesson_date, lesson_time in prepared_rows:
                    timetable_model = TIMETABLES[class_key]
                    class_label = class_names[class_key]
                    existing_lessons = [
                        lesson for lesson in timetable_model.query.filter_by(term=term).all()
                        if normalize_class_name(lesson.classe) == class_key
                        and lesson.subject.casefold() == course.name.casefold()
                    ]
                    if len(existing_lessons) > 1:
                        raise ValueError(
                            f'{course.name} has multiple existing timetable entries in {class_label}; resolve the duplicates first.'
                        )
                    if existing_lessons:
                        lesson = existing_lessons[0]
                        lesson.techername = teacher
                        lesson.date = lesson_date
                        lesson.time = lesson_time
                    else:
                        db.session.add(timetable_model(
                            classe=class_label,
                            term=term,
                            subject=course.name,
                            techername=teacher,
                            date=lesson_date,
                            time=lesson_time,
                        ))
                db.session.commit()
            except ValueError as error:
                db.session.rollback()
                flash(str(error), 'error')
            except SQLAlchemyError:
                db.session.rollback()
                app.logger.exception('Could not save teacher course assignments')
                flash('The teacher assignments could not be saved. Please try again.', 'error')
            else:
                flash(
                    f'{teacher} assigned to {len(prepared_rows)} course/class lesson(s) for {term.title()} term.',
                    'success',
                )
            return redirect(url_for('course_management'))

        flash('Choose a valid course-management action.', 'error')
        return redirect(url_for('course_management'))

    course_catalog = CourseCatalog.query.order_by(CourseCatalog.name).all()
    selected_teacher_id = request.args.get('teacher_id', type=int)
    selected_teacher = (
        db.session.get(Staff, selected_teacher_id)
        if selected_teacher_id else None
    )
    if selected_teacher is not None and not selected_teacher.is_active:
        selected_teacher = None
    course_usage = {}
    for course in course_catalog:
        course_usage[course.id] = sum(
            model.query.filter(
                db.func.lower(model.subject) == course.name.casefold()
            ).count()
            for model in TIMETABLES.values()
        )
    return render_template(
        'course_management.html',
        courses=course_catalog,
        course_usage=course_usage,
        staff_members=Staff.query.filter_by(is_active=True).order_by(Staff.full_name).all(),
        selected_teacher=selected_teacher,
        selected_teacher_assignments=(
            assigned_result_courses(selected_teacher) if selected_teacher else []
        ),
        school_classes=class_names,
        active_page='courses',
    )


@app.route('/admin/portal-settings', methods=['POST'])
@admin_required
def update_portal_settings():
    for portal_name in ('student', 'staff'):
        setting = db.session.get(PortalSetting, portal_name)
        if setting is None:
            setting = PortalSetting(key=portal_name, enabled=True)
            db.session.add(setting)
        setting.enabled = request.form.get(portal_name) == 'enabled'
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception('Could not update portal availability settings')
        flash('Portal access settings could not be updated. Please try again.', 'error')
    else:
        flash('Student and staff portal availability updated.', 'success')
    return redirect(url_for('staff_management'))


@app.route('/tasks', methods=['GET', 'POST'])
def tasks():
    if 'admin_id' in session:
        if request.method == 'POST':
            title = (request.form.get('title') or '').strip()
            description = (request.form.get('description') or '').strip()
            staff_id = request.form.get('staff_id', type=int)
            due_date_value = (request.form.get('due_date') or '').strip()
            staff = db.session.get(Staff, staff_id) if staff_id else None

            try:
                due_date = date.fromisoformat(due_date_value) if due_date_value else None
            except ValueError:
                flash('Enter a valid due date.', 'error')
                return redirect(url_for('tasks'))

            if not title or not description or staff is None or not staff.is_active:
                flash('Enter a title and description, and select an active staff member.', 'error')
            elif len(title) > 160:
                flash('Task titles must be 160 characters or fewer.', 'error')
            else:
                db.session.add(StaffTask(
                    staff_id=staff.id,
                    title=title,
                    description=description,
                    due_date=due_date,
                ))
                db.session.commit()
                flash(f'Task assigned to {staff.full_name}.', 'success')
                return redirect(url_for('tasks'))

        staff_members = (
            Staff.query.filter_by(is_active=True).order_by(Staff.full_name).all()
        )
        assigned_tasks = (
            StaffTask.query.join(StaffTask.assigned_staff)
            .order_by(StaffTask.created_at.desc())
            .all()
        )
        return render_template(
            'tasks.html',
            is_admin=True,
            staff_members=staff_members,
            assigned_tasks=assigned_tasks,
        )

    staff = db.session.get(Staff, session.get('staff_account_id'))
    if staff is None or not staff.is_active or not portal_is_enabled('staff'):
        session.pop('staff_account_id', None)
        return redirect(url_for('schoolAdmin'))

    assigned_tasks = (
        StaffTask.query.filter_by(staff_id=staff.id)
        .order_by(StaffTask.created_at.desc())
        .all()
    )
    return render_template(
        'staff_tasks.html',
        staff=staff,
        assigned_tasks=assigned_tasks,
    )


@app.route('/tasks/<int:task_id>/status', methods=['POST'])
@staff_required
def update_task_status(task_id):
    task = StaffTask.query.filter_by(
        id=task_id, staff_id=g.staff_account.id
    ).first_or_404()
    status = request.form.get('status')
    if status not in {'pending', 'in_progress', 'completed'}:
        flash('Choose a valid task status.', 'error')
    else:
        task.status = status
        db.session.commit()
        flash('Task status updated.', 'success')
    return redirect(url_for('tasks'))


      
    
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'uploads')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_image_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

@app.route('/passport', methods=['GET', 'POST'])
@login_required
def passport():
    email = session.get('user_email', '')

    user_data = admitted.query.filter_by(email=email).first()
    if not user_data:
        session.pop('user_email', None)
        return redirect(url_for('studentlogin'))

    if request.method == 'POST':
        if user_data.is_graduated:
            flash('Graduated student accounts are read-only; passport photos cannot be changed.', 'warning')
            return redirect(url_for('passport'))
        file = request.files.get('passport')
        if file is None or not file.filename:
            flash('Choose a photo to upload.', 'error')
            return redirect(url_for('passport'))
        if not allowed_image_file(file.filename):
            flash('Upload a JPG, PNG, or GIF image.', 'error')
            return redirect(url_for('passport'))

        filename = secure_filename(f"{email}_{file.filename}")
        upload_folder = app.config['UPLOAD_FOLDER']
        try:
            os.makedirs(upload_folder, exist_ok=True)
            file_path = os.path.join(upload_folder, filename)
            file.save(file_path)
        except OSError:
            app.logger.exception('Could not save passport photo for student %s', user_data.id)
            flash('Your passport photo could not be saved. Please try again.', 'error')
            return redirect(url_for('passport'))

        previous_file = user_data.passport_filename
        user_data.passport_filename = filename
        db.session.commit()

        if previous_file and previous_file != filename:
            previous_path = os.path.join(app.config['UPLOAD_FOLDER'], previous_file)
            if os.path.isfile(previous_path):
                os.remove(previous_path)
        flash('Your passport photo has been updated.', 'success')
        return redirect(url_for('passport'))

    passport_url = (
        url_for('uploaded_file', filename=user_data.passport_filename)
        if user_data.passport_filename
        else url_for('static', filename='img/user.jpg')
    )
    return render_template(
        'passport.html',
        student=user_data,
        passport_url=passport_url,
        today=date.today(),
    )

@app.route('/get_current_image', methods=['GET'])
@login_required
def get_current_image():
    email = session.get('user_email', '')
    user_data = admitted.query.filter_by(email=email).first()
    if not user_data or not user_data.passport_filename:
        return jsonify({'filename': 'user.jpg'})

    return jsonify({'filename': user_data.passport_filename})


@app.route('/Biodata', methods=['GET'])
@login_required
def Biodata():
    student = admitted.query.filter_by(email=session['user_email']).first()
    if student is None:
        session.pop('user_email', None)
        return redirect(url_for('studentlogin'))
    return render_template(
        'Biodata.html',
        student=student,
        today=date.today(),
    )
    
@app.route('/checkstatus', methods=['GET', 'POST'])
def checkstatus():
    email = session.get('admission_status_email')
    if not email:
        return redirect(url_for('checkadmin'))

    student = admitted.query.filter(
        db.func.lower(admitted.email) == email
    ).first()
    applicant = None
    if student is None:
        applicant = portal.query.filter(
            db.func.lower(portal.email) == email
        ).first()
    candidate = student or applicant
    if candidate is None:
        session.pop('admission_status_email', None)
        flash('We could not find that application. Please check your details and try again.', 'error')
        return redirect(url_for('checkadmin'))

    return render_template(
        'checkstatus.html',
        candidate=candidate,
        is_admitted=student is not None,
        today=date.today(),
    )

@app.route('/table1', methods=['GET', 'POST'])
@admin_required
def table1():
    if request.method == 'POST':
        action = (request.form.get('action') or 'publish_timetable').strip()
        if action == 'assign_multiple_classes':
            class_keys = request.form.getlist('classes[]')
            term = (request.form.get('term') or '').strip().lower()
            subject = (request.form.get('subject') or '').strip()
            teacher = (request.form.get('teacher') or '').strip()
            lesson_date = (request.form.get('date') or '').strip()
            lesson_time = (request.form.get('time') or '').strip()
            active_staff_names = {
                staff.full_name
                for staff in Staff.query.filter_by(is_active=True).all()
            }
            if (
                not class_keys
                or len(set(class_keys)) != len(class_keys)
                or any(class_key not in TIMETABLE_CLASS_NAMES for class_key in class_keys)
                or term not in {'first', 'second', 'third'}
                or not subject
                or len(subject) > 100
                or teacher not in active_staff_names
                or not lesson_date
                or not lesson_time
            ):
                flash('Choose one or more valid classes, a term, subject, active teacher, date, and time.', 'error')
                return redirect(url_for('table1'))

            try:
                parsed_date = date.fromisoformat(lesson_date)
                parsed_time = datetime.strptime(lesson_time, '%H:%M').time()
            except ValueError:
                flash('Enter a valid lesson date and time.', 'error')
                return redirect(url_for('table1'))

            for class_key in class_keys:
                db.session.add(TIMETABLES[class_key](
                    classe=TIMETABLE_CLASS_NAMES[class_key],
                    term=term,
                    subject=subject,
                    techername=teacher,
                    date=parsed_date,
                    time=parsed_time,
                ))
            try:
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                app.logger.exception('Could not assign teacher course across classes')
                flash('The teacher assignment could not be saved. Please try again.', 'error')
            else:
                flash(
                    f'{teacher} assigned to teach {subject} in {len(class_keys)} classes for {term.title()} term.',
                    'success',
                )
            return redirect(url_for('table1'))

        classe = (request.form.get('classe') or '').strip().lower()
        term = (request.form.get('term') or '').strip().lower()
        subjects = request.form.getlist('subject[]')
        teachers = request.form.getlist('techername[]')
        dates = request.form.getlist('date[]')
        times = request.form.getlist('time[]')

        table_class = TIMETABLES.get(classe)
        if classe not in TIMETABLE_CLASS_NAMES:
            table_class = None
        if table_class is None or term not in {'first', 'second', 'third'}:
            flash('Select a valid class and term.', 'error')
            return redirect(url_for('table1'))
        if not subjects or not (
            len(subjects) == len(teachers) == len(dates) == len(times)
        ):
            flash('Add at least one complete lesson to the timetable.', 'error')
            return redirect(url_for('table1'))
        if any(
            not subject.strip() or not teacher.strip() or not lesson_date or not lesson_time
            for subject, teacher, lesson_date, lesson_time
            in zip(subjects, teachers, dates, times)
        ):
            flash('Complete every subject, teacher, date, and time field.', 'error')
            return redirect(url_for('table1'))

        active_staff_names = {
            staff.full_name for staff in Staff.query.filter_by(is_active=True).all()
        }
        if any(teacher not in active_staff_names for teacher in teachers):
            flash('Select a teacher from the active staff list.', 'error')
            return redirect(url_for('table1'))

        try:
            for subject, teacher, lesson_date, lesson_time in zip(
                subjects, teachers, dates, times
            ):
                entry = table_class(
                    classe=TIMETABLE_CLASS_NAMES[classe],
                    term=term,
                    subject=subject,
                    techername=teacher,
                    date=date.fromisoformat(lesson_date),
                    time=datetime.strptime(lesson_time, '%H:%M').time(),
                )
                db.session.add(entry)
            db.session.commit()
        except ValueError:
            db.session.rollback()
            flash('Enter a valid lesson date and time.', 'error')
            return redirect(url_for('table1'))

        flash('Timetable published successfully.', 'success')
        return redirect(url_for('table1'))

    staff_names = [
        staff.full_name
        for staff in Staff.query.filter_by(is_active=True).order_by(Staff.full_name).all()
    ]
    class_names = TIMETABLE_CLASS_NAMES
    selected_class = (request.args.get('class') or '').strip().lower()
    selected_term = (request.args.get('term') or 'first').strip().lower()
    if selected_class not in TIMETABLE_CLASS_NAMES:
        selected_class = ''
    if selected_term not in {'first', 'second', 'third'}:
        selected_term = 'first'
    selected_students = (
        result_roster(class_names[selected_class])
        if selected_class else []
    )
    timetable_entries = []
    if selected_class:
        timetable_entries = sorted(
            (
                lesson for lesson in TIMETABLES[selected_class].query.filter_by(term=selected_term).all()
                if normalize_class_name(lesson.classe) == selected_class
            ),
            key=lambda lesson: (lesson.date, lesson.time, lesson.subject.casefold()),
        )
    course_options = sorted(
        {
            lesson.subject.strip()
            for timetable_model in TIMETABLES.values()
            for lesson in timetable_model.query.all()
            if lesson.subject and lesson.subject.strip()
        } | {course.name for course in CourseCatalog.query.all()},
        key=str.casefold,
    )
    return render_template(
        'table1.html',
        staff_names=staff_names,
        school_classes=class_names,
        selected_class=selected_class,
        selected_term=selected_term,
        selected_students=selected_students,
        timetable_entries=timetable_entries,
        course_options=course_options,
    )


@app.route('/my-invoices', methods=['GET'])
@login_required
def my_invoices():
    student = admitted.query.filter_by(email=session['user_email']).first()
    if student is None:
        session.pop('user_email', None)
        return redirect(url_for('studentlogin'))
    invoices = student_class_invoices(student)
    return render_template(
        'student_invoices.html',
        student=student,
        invoices=invoices,
        invoice_count=len(invoices),
        today=date.today(),
    )


@app.route('/student/results', methods=['GET'])
@login_required
def student_results():
    student = admitted.query.filter_by(email=session['user_email']).first()
    if student is None:
        session.pop('user_email', None)
        return redirect(url_for('studentlogin'))

    class_key = normalize_class_name(student.entry_class)
    approvals = CourseResultApproval.query.order_by(
        CourseResultApproval.approved_at.desc()
    ).all()
    all_reports = []
    for approval in approvals:
        grades = CourseGrade.query.filter_by(
            student_id=student.id,
            timetable_class=approval.timetable_class,
            term=approval.term,
            subject=approval.subject,
        ).order_by(CourseGrade.subject).all()
        if approval.timetable_class != class_key and not grades:
            continue
        if grades:
            all_reports.append({'approval': approval, 'grades': grades})
    term_order = {'first': 0, 'second': 1, 'third': 2}
    term_options = sorted(
        {report['approval'].term for report in all_reports},
        key=lambda term: (term_order.get(term.casefold(), 3), term.casefold()),
    )
    requested_term = (request.args.get('term') or 'all').strip()
    selected_term = (
        requested_term
        if requested_term == 'all' or requested_term in term_options
        else 'all'
    )
    reports = [
        report for report in all_reports
        if selected_term == 'all' or report['approval'].term == selected_term
    ]
    return render_template(
        'student_results.html',
        student=student,
        reports=reports,
        term_options=term_options,
        selected_term=selected_term,
        invoice_count=len(student_class_invoices(student)),
        today=date.today(),
    )
        
@app.route('/studentlogin', methods=['GET', 'POST'])
def studentlogin():
    if not portal_is_enabled('student'):
        session.pop('user_email', None)
        return render_template(
            'studentlogin.html',
            error_message='The student portal is temporarily unavailable. Please contact the school office.',
            now=datetime.now(),
            portal_disabled=True,
        )
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        admission_id = (request.form.get('admission_id') or '').strip()

        user = admitted.query.filter(
            db.func.lower(admitted.email) == email,
            admitted.admission_id == admission_id,
        ).first()

        if user:
            # Email and admission number match, set user email in session
            session.pop('admin_id', None)
            session.pop('staff_account_id', None)
            session['user_email'] = email
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            # Authentication failed, show an error message
            error_message = "Invalid email or admission number."
            return render_template(
                'studentlogin.html',
                error_message=error_message,
                now=datetime.now(),
                portal_disabled=False,
            )

    # Render the studentlogin template with any existing error message
    error_message = request.args.get('error_message', '')
    return render_template(
        'studentlogin.html',
        error_message=error_message,
        now=datetime.now(),
        portal_disabled=False,
    )


# Function to extract candidate details from PDF content
def extract_candidate_details(pdf_text):
    name_pattern = re.compile(r"candidate Name:\s*(.+)")
    registration_pattern = re.compile(r"RegistrationNumber:\s*(\w+)")
    exam_year_pattern = re.compile(r"ExamYear:\s*(\d{4})")

    name_match = name_pattern.search(pdf_text)
    registration_match = registration_pattern.search(pdf_text)
    exam_year_match = exam_year_pattern.search(pdf_text)

    candidate_details = {
        'candidate Name': name_match.group(1) if name_match else 'Unknown',
        'registration_number': registration_match.group(1) if registration_match else 'Unknown',
        'exam_year': exam_year_match.group(1) if exam_year_match else 'Unknown',
    }
    return candidate_details

@app.route('/checkresult', methods=['POST', 'GET'])
@login_required
def check_result():
    student = admitted.query.filter_by(email=session['user_email']).first()
    if student is None:
        session.pop('user_email', None)
        return redirect(url_for('studentlogin'))

    if request.method == 'POST':
        registration_number = (request.form.get('registrationnumber') or '').strip()
        exam_year = (request.form.get('examyear') or '').strip()
        if not registration_number or not exam_year.isdigit() or len(exam_year) != 4:
            flash('Enter an examination number and a valid four-digit examination year.', 'error')
            return redirect(url_for('check_result'))

        files = os.listdir(RESULTS_FOLDER)
        for filename in sorted(files):
            if filename.lower().endswith('.pdf'):
                file_path = os.path.join(RESULTS_FOLDER, filename)
                try:
                    reader = PyPDF2.PdfReader(file_path)
                    pdf_text = ''.join(page.extract_text() or '' for page in reader.pages)
                    if registration_number in pdf_text and exam_year in pdf_text:
                        return send_file(file_path, as_attachment=False)
                except (PyPDF2.errors.PdfReadError, OSError, ValueError) as error:
                    app.logger.warning('Unable to read result PDF %s: %s', filename, error)
        flash('No result matched that examination number and year.', 'error')
        return redirect(url_for('check_result'))
    return render_template(
        'checkresult.html',
        student=student,
        invoice_count=len(student_class_invoices(student)),
        current_year=date.today().year,
        today=date.today(),
    )
        
@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    # Fetch user email from session
    email = session.get('user_email', '')

    # Fetch username from the database based on the provided email
    student = admitted.query.filter_by(email=email).first()
    if student is None:
        session.pop('user_email', None)
        return redirect(url_for('studentlogin'))
    username = student.username
    first_name = student.firstName
    lastName = student.lastName
    admission_id = student.admission_id
    entry_session = student.entry_session
    entry_class = student.entry_class

    success_message = request.args.get('success_message', '')
    candidate_details = request.args.get('candidate_details', None)
    filename = request.args.get('filename', None)

    if candidate_details:
        candidate_details = ast.literal_eval(candidate_details)  # Convert string back to dictionary

    # Fetch total number of registered students
    total_students = portal.query.count()

    invoices = student_class_invoices(student)
    return render_template(
        'dashboard.html',
        student=student,
        success_message=success_message,
        username=username,
        firstName=first_name,
        total_students=total_students,
        candidate_details=candidate_details,
        filename=filename,
        lastName=lastName,
        admission_id=admission_id,
        entry_session=entry_session,
        entry_class=entry_class,
        invoice_count=len(invoices),
        recent_invoices=invoices[:3],
        today=date.today(),
        now=datetime.now(),
    )
@app.route('/logout')
def logout():
    # Remove user email from session
    session.pop('user_email', None)
    return redirect(url_for('studentlogin'))

@app.route('/logout1')
def logout1():
    session.pop('admin_id', None)
    session.pop('staff_account_id', None)
    return redirect(url_for('schoolAdmin'))


@app.route('/checkadmin', methods=['POST','GET'])
def checkadmin():
    if request.method == 'POST':
        lookup = (request.form.get('lookup') or '').strip()
        entry_session = (request.form.get('entry_session') or '').strip()
        if not lookup or not entry_session or len(entry_session) > 30:
            flash('Enter your application reference or email and select a valid session.', 'error')
            return redirect(url_for('checkadmin'))

        email_lookup = lookup.casefold()
        applicant = portal.query.filter(
            portal.entry_session == entry_session,
            db.or_(
                db.func.lower(portal.email) == email_lookup,
                portal.admission_id == lookup,
            ),
        ).first()
        student = admitted.query.filter(
            admitted.entry_session == entry_session,
            db.or_(
                db.func.lower(admitted.email) == email_lookup,
                admitted.admission_id == lookup,
            ),
        ).first()
        candidate = student or applicant
        if candidate:
            session['admission_status_email'] = candidate.email.casefold()
            return redirect(url_for('checkstatus'))

        flash('No application matched those details and session. Check them and try again.', 'error')
        return redirect(url_for('checkadmin'))

    return render_template(
        'checkadmin.html',
        school_sessions=SCHOOL_SESSIONS,
        selected_session=request.args.get('entry_session', ''),
    )


@app.route('/Adminlist', methods=['GET', 'POST'])
@admin_required
def Adminlist():
    if request.method == 'GET':
        accepted_emails = db.session.query(db.func.lower(admitted.email))
        users = portal.query.filter(
            ~db.func.lower(portal.email).in_(accepted_emails)
        ).order_by(portal.firstName, portal.lastName).all()
        return render_template('Adminlist.html', users=users)

    elif request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        applicant = (
            portal.query.filter(db.func.lower(portal.email) == email).first()
            if email else None
        )
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        if applicant is None:
            if is_ajax:
                return jsonify({'message': 'The application could not be found.'}), 404
            flash('The application could not be found.', 'error')
            return redirect(url_for('Adminlist'))

        existing_user = admitted.query.filter(
            db.func.lower(admitted.email) == email
        ).first()
        if existing_user:
            if is_ajax:
                return jsonify({'message': 'This applicant has already been admitted.'}), 409
            flash('This applicant has already been admitted.', 'error')
            return redirect(url_for('Adminlist'))

        try:
            student = admitted(
                username=applicant.username,
                email=email,
                firstName=applicant.firstName,
                lastName=applicant.lastName,
                dob=applicant.dob,
                gender=applicant.gender,
                birth_certificate=applicant.birth_certificate,
                payment_evidence=applicant.payment_evidence,
                state_origin=applicant.state_origin,
                entry_class=applicant.entry_class,
                entry_session=applicant.entry_session,
                recent_result=applicant.recent_result,
                phone_number=applicant.phone_number,
                address=applicant.address,
                admission_id=applicant.admission_id,
                guardian_name=applicant.guardian_name,
            )
            db.session.add(student)
            class_fee_rates = [
                schedule
                for schedule in FeeSchedule.query.order_by(FeeSchedule.fee_type).all()
                if normalize_class_name(schedule.class_name)
                == normalize_class_name(student.entry_class)
            ]
            issued_invoices = [
                FeeInvoice(
                    student=student,
                    fee_type=schedule.fee_type,
                    description='Class fee rate',
                    class_name=student.entry_class,
                    school_session=student.entry_session,
                    amount=schedule.amount,
                )
                for schedule in class_fee_rates
            ]
            db.session.add_all(issued_invoices)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception('Could not admit applicant %s', applicant.email)
            if is_ajax:
                return jsonify({'message': 'The applicant could not be admitted. Please try again.'}), 500
            flash('The applicant could not be admitted. Please try again.', 'error')
            return redirect(url_for('Adminlist'))

        invoice_setup_failed = False
        additional_invoice_count = 0
        try:
            additional_invoices = ensure_student_class_invoices(student)
            additional_invoice_count = len(additional_invoices)
        except SQLAlchemyError:
            invoice_setup_failed = True
            app.logger.exception(
                'Student %s was admitted, but class invoice preparation failed',
                student.id,
            )

        mail_sent = send_email(
            applicant.email,
            'Your Florence Court admission is approved',
            (
                f'Hello {applicant.firstName},\n\n'
                'Your admission to Florence Court has been approved.\n'
                'Sign in to the student portal using:\n'
                f'Email address: {applicant.email}\n'
                f'Admission ID: {applicant.admission_id}\n\n'
                'Keep your admission ID private. You can sign in from the Student Login page.'
            ),
        )
        invoice_email_failures = sum(
            not email_fee_invoice(invoice)
            for invoice in issued_invoices
        )
        if is_ajax:
            response = {'message': 'Student admitted successfully.'}
            if not mail_sent:
                response['email_warning'] = 'Admission was saved, but the login email could not be sent.'
            if invoice_setup_failed:
                response['fee_warning'] = (
                    'Admission was saved, but class invoices could not be prepared. '
                    'They will be retried when the student opens Fees & invoices.'
                )
            if invoice_email_failures:
                response.setdefault('fee_warning', (
                    f'{invoice_email_failures} class fee invoice email(s) could not be sent; '
                    'the invoices are available in the student portal.'
                ))
            return jsonify(response)
        if not mail_sent:
            flash(
                f'{applicant.firstName} {applicant.lastName} was admitted, but the login email could not be sent. Check the mail settings and logs.',
                'warning',
            )
        elif invoice_setup_failed or invoice_email_failures:
            flash(
                f'{applicant.firstName} {applicant.lastName} admitted successfully; login details emailed. '
                + (
                    'Class invoices could not be prepared and will be retried when the student opens Fees & invoices. '
                    if invoice_setup_failed else ''
                )
                + (
                    f'{invoice_email_failures} class fee invoice email(s) could not be sent.'
                    if invoice_email_failures else ''
                ),
                'warning',
            )
        else:
            invoice_count = len(issued_invoices) + additional_invoice_count
            flash(
                f'{applicant.firstName} {applicant.lastName} admitted successfully; login details emailed.'
                + (f' {invoice_count} class fee invoice(s) were added to the student portal.' if invoice_count else ''),
                'success',
            )
        return redirect(url_for('Adminlist'))

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    if secure_filename(filename) != filename:
        abort(404)

    is_admin = 'admin_id' in session
    student = admitted.query.filter_by(
        email=session.get('user_email', '')
    ).first() if session.get('user_email') else None
    owns_passport = bool(
        student
        and student.passport_filename == filename
    )
    if not is_admin and not owns_passport:
        abort(404)
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/results/<path:filename>')
@admin_required
def result_file(filename):
    return send_from_directory(RESULTS_FOLDER, filename)




@app.route('/table', methods=['GET', 'POST'])
@login_required
def table():
    email = session.get('user_email', '')
    user_data = admitted.query.filter_by(email=email).first()
    if user_data is None:
        session.pop('user_email', None)
        return redirect(url_for('studentlogin'))
    allowed_class = normalize_class_name(user_data.entry_class)
    requested_class = request.values.get('classe', user_data.entry_class)
    if normalize_class_name(requested_class) != allowed_class:
        flash('You can only view the timetable for your enrolled class.', 'error')
        return redirect(url_for('table'))
    term_options = ('first', 'second', 'third')
    selected_term = (request.values.get('term') or '').strip().casefold()
    if selected_term and selected_term not in term_options:
        flash('Choose a valid academic term.', 'error')
        selected_term = ''
    fetched_data = []
    if selected_term:
        TableClass = TIMETABLES.get(allowed_class)
        if TableClass:
            fetched_data = sorted(
                (
                    lesson for lesson in TableClass.query.filter_by(term=selected_term).all()
                    if normalize_class_name(lesson.classe) == allowed_class
                ),
                key=lambda lesson: (lesson.date, lesson.time),
            )

    return render_template(
        'table.html',
        student=user_data,
        fetched_data=fetched_data,
        selected_term=selected_term,
        term_options=term_options,
        invoice_count=len(student_class_invoices(user_data)),
        today=date.today(),
    )

@app.route('/payment', methods=['POST', 'GET'])
@login_required
def payment():
    return redirect(url_for('my_invoices'))

@app.route('/get_username', methods=['POST'])
def get_username():
    admission_id = request.form.get('admission_id')
    user_data = portal.query.filter_by(admission_id=admission_id).first()

    if user_data:
        return jsonify(username=user_data.username)
    else:
        return jsonify(username=None)


@app.route('/forgot', methods=['GET', 'POST'])
def forgot():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        if not email:
            flash('Enter the email address linked to your staff account.', 'error')
            return redirect(url_for('forgot'))

        staff = Staff.query.filter(db.func.lower(Staff.email) == email).first()
        if staff is None:
            student_account = admitted.query.filter(
                db.func.lower(admitted.email) == email
            ).first()
            if student_account:
                flash(
                    'Student sign-in uses your registered email and admission number. Contact the school office if you need help with your admission number.',
                    'info',
                )
            else:
                flash('No staff account was found for that email address.', 'error')
            return redirect(url_for('forgot'))

        code = f'{secrets.randbelow(1_000_000):06d}'
        challenge = PasswordResetChallenge(
            staff_id=staff.id,
            code_hash=hashlib.sha256(code.encode('ascii')).hexdigest(),
            expires_at=datetime.now() + timedelta(minutes=15),
        )
        try:
            PasswordResetChallenge.query.filter_by(staff_id=staff.id).delete()
            db.session.add(challenge)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception('Could not create password reset challenge for staff %s', staff.id)
            flash('A reset code could not be created. Please try again.', 'error')
            return redirect(url_for('forgot'))

        if not send_email(
            staff.email,
            'Your Florence Court password reset code',
            (
                f'Hello {staff.full_name},\n\n'
                f'Your password reset code is {code}.\n'
                'Enter this code on the password reset page within 15 minutes. '
                'If you did not request this code, you can ignore this email.'
            ),
        ):
            db.session.delete(challenge)
            db.session.commit()
            flash('The reset email could not be sent. Check the email settings and try again.', 'error')
            return redirect(url_for('forgot'))

        session['password_reset_challenge_id'] = challenge.id
        flash('A 6-digit reset code has been sent to your staff email address.', 'success')
        return redirect(url_for('reset'))

    return render_template('forgot.html')


def current_password_reset_challenge():
    challenge_id = session.get('password_reset_challenge_id')
    if not challenge_id:
        return None
    challenge = db.session.get(PasswordResetChallenge, challenge_id)
    if challenge is None or challenge.expires_at <= datetime.now():
        if challenge is not None:
            db.session.delete(challenge)
            db.session.commit()
        session.pop('password_reset_challenge_id', None)
        session.pop('password_reset_verified_id', None)
        return None
    return challenge


@app.route('/reset', methods=['GET', 'POST'])
def reset():
    challenge = current_password_reset_challenge()
    if challenge is None:
        flash('Request a new password reset code to continue.', 'warning')
        return redirect(url_for('forgot'))

    if request.method == 'POST':
        code = (request.form.get('code') or '').strip()
        candidate_hash = hashlib.sha256(code.encode('utf-8')).hexdigest()
        if len(code) != 6 or not code.isdigit() or not hmac.compare_digest(
            challenge.code_hash, candidate_hash
        ):
            challenge.failed_attempts += 1
            if challenge.failed_attempts >= 5:
                db.session.delete(challenge)
                session.pop('password_reset_challenge_id', None)
                session.pop('password_reset_verified_id', None)
                flash('Too many incorrect codes. Request a new reset code to continue.', 'error')
            else:
                flash('That reset code is invalid. Check the email and try again.', 'error')
            try:
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                app.logger.exception('Could not record password reset verification attempt')
                flash('The code could not be checked. Please try again.', 'error')
            if challenge.failed_attempts >= 5:
                return redirect(url_for('forgot'))
        else:
            session['password_reset_verified_id'] = challenge.id
            return redirect(url_for('resetpassword'))

    staff = db.session.get(Staff, challenge.staff_id)
    return render_template(
        'reset.html',
        staff_email=staff.email if staff else '',
        expires_at=challenge.expires_at,
    )


@app.route('/resetpassword', methods=['GET', 'POST'])
def resetpassword():
    challenge = current_password_reset_challenge()
    if (
        challenge is None
        or session.get('password_reset_verified_id') != challenge.id
    ):
        flash('Verify a current reset code before choosing a new password.', 'warning')
        return redirect(url_for('forgot'))
    staff = db.session.get(Staff, challenge.staff_id)
    if staff is None:
        db.session.delete(challenge)
        db.session.commit()
        session.pop('password_reset_challenge_id', None)
        session.pop('password_reset_verified_id', None)
        flash('That staff account is no longer available. Contact the school administrator.', 'error')
        return redirect(url_for('schoolAdmin'))

    if request.method == 'POST':
        new_password = request.form.get('password') or ''
        confirm_password = request.form.get('confirm_password') or ''
        if new_password != confirm_password:
            flash('Passwords do not match.', 'error')
        elif len(new_password) < 8:
            flash('Choose a password with at least 8 characters.', 'error')
        else:
            staff.password_hash = hash_password(new_password)
            db.session.delete(challenge)
            try:
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                app.logger.exception('Could not save staff password reset for staff %s', staff.id)
                flash('Your password could not be updated. Please try again.', 'error')
            else:
                session.pop('password_reset_challenge_id', None)
                session.pop('password_reset_verified_id', None)
                flash('Password updated. Sign in with your staff ID and new password.', 'success')
                return redirect(url_for('schoolAdmin'))

    return render_template('resetpassword.html', staff_email=staff.email)

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    email = session.get('user_email', '')

    # Fetch user data directly from the database based on the provided email
    user_data = portal.query.filter_by(email=email).first()

    # Check if there is data returned from the query
    if user_data:
        username, email, lastName,firstName = user_data.username, user_data.email, user_data.lastName,user_data.firstName
    else:
        username, email, lastName,firstName = None, None, None,None

    success_message = request.args.get('success_message', '')

    # Fetch total number of registered students
    total_students = user_data

    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        # Check if the current password matches the one in the database
        if current_password == user_data.password:
            # Current password is correct, proceed to update the password
            if new_password == confirm_password:
                # Update the user's password in the database
                user_data.password = new_password
                db.session.commit()

                flash('Password successfully changed!', 'success')
                return redirect(url_for('dashboard', success_message='Password successfully changed!'))
            else:
                flash('New password and confirm password do not match!', 'error')
        else:
            flash('Incorrect current password. Please try again.', 'error')

    return render_template('profile.html', success_message=success_message, username=username, email=email,
                           lastName=lastName,firstName=firstName, total_students=total_students)

import os

from werkzeug.utils import secure_filename

# Configure the folder for file uploads
UPLOAD_FOLDER = os.environ.get(
    'UPLOAD_FOLDER',
    os.path.join(app.root_path, 'uploads'),
)
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
NIGERIAN_STATES = (
    'Abia', 'Adamawa', 'Akwa Ibom', 'Anambra', 'Bauchi', 'Bayelsa', 'Benue',
    'Borno', 'Cross River', 'Delta', 'Ebonyi', 'Edo', 'Ekiti', 'Enugu',
    'Federal Capital Territory', 'Gombe', 'Imo', 'Jigawa', 'Kaduna', 'Kano',
    'Katsina', 'Kebbi', 'Kogi', 'Kwara', 'Lagos', 'Nasarawa', 'Niger',
    'Ogun', 'Ondo', 'Osun', 'Oyo', 'Plateau', 'Rivers', 'Sokoto', 'Taraba',
    'Yobe', 'Zamfara',
)
SCHOOL_SESSIONS = tuple(
    f'{year}/{year + 1}'
    for year in range(date.today().year - 1, date.today().year + 5)
)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/apply', methods=['GET', 'POST'])
def apply():
    def generate_number():
        return str(random.randint(10000, 99999))

    # For GET request, generate a new number
    numbers_str = generate_number()
    selected_session = request.form.get('entry_session', '')
    
    if request.method == 'POST':
        try:
            username = request.form.get('username')
            firstName = request.form.get('firstName')
            lastName = request.form.get('lastName')
            email = request.form.get('email')
           
            dob = request.form.get('dob')
            state_origin = request.form.get('state_origin')
            gender = request.form.get('gender')
            entry_class = request.form.get('entry_class')
            entry_session = request.form.get('entry_session')
            admission_id = request.form.get('admission_id')
            guardian_name = request.form.get('guardian_name')
            phone_number = request.form.get('phone_number')
            address = request.form.get('address')
            
            # Check if any required field is empty
            if not (username and firstName and  lastName and email and dob and gender and state_origin and entry_class and entry_session and phone_number and address and admission_id and guardian_name):
                return render_template(
                    'apply.html',
                    error_message="All fields are required.",
                    numbers_str=numbers_str,
                    states=NIGERIAN_STATES,
                    school_sessions=SCHOOL_SESSIONS,
                    selected_session=selected_session,
                )

            if state_origin not in NIGERIAN_STATES or gender not in {'M', 'F'}:
                return render_template(
                    'apply.html',
                    error_message="Select a valid state of origin and gender.",
                    numbers_str=numbers_str,
                    states=NIGERIAN_STATES,
                    school_sessions=SCHOOL_SESSIONS,
                    selected_session=selected_session,
                )

            if entry_session not in SCHOOL_SESSIONS:
                return render_template(
                    'apply.html',
                    error_message="Select a valid school session.",
                    numbers_str=numbers_str,
                    states=NIGERIAN_STATES,
                    school_sessions=SCHOOL_SESSIONS,
                    selected_session='',
                )

            entry_class_option = next(
                (class_name for class_name in SCHOOL_CLASSES
                 if class_name.casefold() == (entry_class or '').casefold()),
                None,
            )
            if entry_class_option is None:
                return render_template(
                    'apply.html',
                    error_message='Select a valid class of entry.',
                    numbers_str=numbers_str,
                    states=NIGERIAN_STATES,
                    school_sessions=SCHOOL_SESSIONS,
                    selected_session=selected_session,
                )
            entry_class = entry_class_option

            if len(admission_id) != 5 or not admission_id.isdigit():
                return render_template(
                    'apply.html',
                    error_message="The application reference must be 5 digits.",
                    numbers_str=numbers_str,
                    states=NIGERIAN_STATES,
                    school_sessions=SCHOOL_SESSIONS,
                    selected_session=selected_session,
                )

            # Handle file uploads
            birth_certificate_file = request.files['birth_certificate']
            recent_result_file = request.files['recent_result']

            if not (birth_certificate_file and recent_result_file):
                return render_template(
                    'apply.html',
                    error_message="All files are required.",
                    numbers_str=numbers_str,
                    states=NIGERIAN_STATES,
                    school_sessions=SCHOOL_SESSIONS,
                    selected_session=selected_session,
                )

            # Check if files are allowed
            if not (allowed_file(birth_certificate_file.filename) and allowed_file(recent_result_file.filename)):
                return render_template(
                    'apply.html',
                    error_message="File type not allowed.",
                    numbers_str=numbers_str,
                    states=NIGERIAN_STATES,
                    school_sessions=SCHOOL_SESSIONS,
                    selected_session=selected_session,
                )

            # Secure filenames
            birth_certificate_filename = secure_filename(birth_certificate_file.filename)
            recent_result_filename = secure_filename(recent_result_file.filename)

            # Save files
            birth_certificate_path = os.path.join(app.config['UPLOAD_FOLDER'], birth_certificate_filename)
            recent_result_path = os.path.join(app.config['UPLOAD_FOLDER'], recent_result_filename)

            birth_certificate_file.save(birth_certificate_path)
            recent_result_file.save(recent_result_path)

            # Insert the new user into the database
            new_user = portal(username=username, email=email, firstName=firstName, lastName=lastName, dob=dob, gender=gender, birth_certificate=birth_certificate_filename, recent_result=recent_result_filename, payment_evidence='', state_origin=state_origin, entry_class=entry_class, entry_session=entry_session, phone_number=phone_number, address=address, admission_id=admission_id, guardian_name=guardian_name)
            db.session.add(new_user)
            db.session.commit()

            mail_sent = send_email(
                email,
                'We received your Florence Court application',
                (
                    f'Hello {firstName},\n\n'
                    'Thank you for applying to Florence Court International Schools. '
                    'Your application has been received and is awaiting review.\n'
                    f'Application reference: {admission_id}\n\n'
                    'We will contact you by email when the school has reviewed your application.'
                ),
            )
            if mail_sent:
                flash('Your application was submitted. A confirmation email has been sent.', 'success')
            else:
                flash(
                    'Your application was submitted, but its confirmation email could not be sent. The school will still review it.',
                    'warning',
                )
            return redirect(url_for('index'))

        except Exception as e:
            print(f"Error during registration: {str(e)}")
            return render_template(
                'apply.html',
                error_message=str(e),
                numbers_str=numbers_str,
                states=NIGERIAN_STATES,
                school_sessions=SCHOOL_SESSIONS,
                selected_session=selected_session,
            )

    return render_template(
        'apply.html',
        numbers_str=numbers_str,
        states=NIGERIAN_STATES,
        school_sessions=SCHOOL_SESSIONS,
        selected_session=selected_session,
    )


def send_email(receiver_email, subject, message):
    smtp_host = app.config.get('MAIL_SERVER')
    smtp_port = app.config.get('MAIL_PORT')
    smtp_username = app.config.get('MAIL_USERNAME')
    smtp_password = app.config.get('MAIL_PASSWORD')
    sender_email = app.config.get('MAIL_SENDER')
    if not all((smtp_host, smtp_port, smtp_username, smtp_password, sender_email)):
        app.logger.warning('Email to %s was not sent because mail settings are incomplete.', receiver_email)
        return False

    plain_message = MIMEMultipart('alternative')
    plain_message['Subject'] = subject
    plain_message['From'] = sender_email
    plain_message['To'] = receiver_email
    plain_message.attach(MIMEText(message, 'plain', 'utf-8'))
    escaped_message = html.escape(message).replace('\n', '<br>')
    html_message = (
        '<!doctype html><html><body style="margin:0;background:#f3f6fa;'
        'font-family:Arial,sans-serif;color:#23344d">'
        '<div style="max-width:600px;margin:28px auto;padding:0 16px">'
        '<div style="padding:20px 24px;background:#142d4e;color:#fff;border-radius:12px 12px 0 0">'
        '<strong style="font-size:18px">Florence Court</strong>'
        '<div style="margin-top:4px;color:#d7e4f5;font-size:12px">International Schools</div></div>'
        '<div style="padding:24px;background:#fff;border:1px solid #e1e8f0;border-top:0;'
        'border-radius:0 0 12px 12px"><h1 style="margin:0 0 16px;font-size:20px">'
        f'{html.escape(subject)}</h1><p style="line-height:1.7">{escaped_message}</p>'
        '<hr style="border:0;border-top:1px solid #e7edf4;margin:22px 0">'
        '<small style="color:#6b7c91">Florence Court International Schools</small></div></div>'
        '</body></html>'
    )
    html_part = MIMEMultipart('related')
    html_part.attach(MIMEText(html_message, 'html', 'utf-8'))
    plain_message.attach(html_part)
    try:
        smtp_class = (
            smtplib.SMTP_SSL
            if app.config.get('MAIL_USE_SSL')
            else smtplib.SMTP
        )
        smtp_options = {'timeout': 8}
        if app.config.get('MAIL_USE_SSL'):
            smtp_options['context'] = ssl.create_default_context()
        with smtp_class(smtp_host, smtp_port, **smtp_options) as server:
            if app.config.get('MAIL_USE_TLS', True) and not app.config.get('MAIL_USE_SSL'):
                server.starttls()
                server.ehlo()
            server.login(smtp_username, smtp_password)
            server.sendmail(sender_email, receiver_email, plain_message.as_string())
        return True
    except (smtplib.SMTPException, OSError, ValueError):
        app.logger.exception('Could not send email to %s', receiver_email)
        return False

if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG', '').strip().lower() == 'true')