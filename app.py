from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
import datetime
import random # Not used currently, but often useful
import io
import csv
import json
import logging # For better logging on Render

# --- Application Setup ---
app = Flask(__name__)

# --- Logging Setup for Render ---
# You can set log level via Gunicorn or here.
# Gunicorn's --log-level debug might be more comprehensive.
# logging.basicConfig(level=logging.INFO) # Basic setup
# Or, for more Flask-specific logging:
if not app.debug: # Only use this when not in Flask debug mode (i.e., on Render)
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    app.logger.addHandler(stream_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('SATInsight App Starting Up on Render')

# --- SECRET_KEY Configuration ---
# CRITICAL FOR RENDER: Ensure 'SECRET_KEY' is set in your Render environment variables.
# The os.urandom(24) fallback is for local dev and will break sessions on Render if used.
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
if not app.config['SECRET_KEY']:
    app.logger.warning("SECRET_KEY is not set in environment. Using a temporary key for local dev. THIS IS INSECURE FOR PRODUCTION.")
    app.config['SECRET_KEY'] = os.urandom(24).hex()


# --- Database Configuration ---
# CRITICAL FOR RENDER: Ensure 'DATABASE_URL' is set in Render env vars if using Render's PostgreSQL.
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    app.logger.info(f"DATABASE_URL found: {DATABASE_URL[:30]}...") # Log part of it for verification
    if DATABASE_URL.startswith("postgres://"):
        # Heroku/Render style: SQLAlchemy expects postgresql://
        app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        app.logger.info("Postgres (Heroku/Render style) configured.")
    elif DATABASE_URL.startswith("postgresql://"):
        app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
        app.logger.info("PostgreSQL (standard) configured.")
    # Add other database types if needed, e.g., mysql
    # elif DATABASE_URL.startswith("mysql://"):
    #     app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    #     app.logger.info("MySQL configured.")
    else: # Could be SQLite or other, or an improperly formatted URL
        app.logger.warning(f"DATABASE_URL format not recognized for special handling, using as is: {DATABASE_URL}")
        app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL # Use as is if not postgres
else:
    # Local SQLite fallback
    app.logger.info("DATABASE_URL not found. Falling back to local SQLite database: sattest.db")
    instance_path = os.path.join(app.instance_path)
    if not os.path.exists(instance_path):
        try:
            os.makedirs(instance_path)
            app.logger.info(f"Created instance folder: {instance_path}")
        except OSError as e:
            app.logger.error(f"Could not create instance folder {instance_path}: {e}", exc_info=True)
            # This could be a critical error if SQLite cannot be created.
    
    # IMPORTANT for Render if using SQLite: Render's filesystem is often ephemeral.
    # Data might not persist across deploys/restarts. Consider this path carefully.
    # /var/data is a common persistent directory on some platforms, check Render docs if needed.
    # For Render, it's highly recommended to use their managed PostgreSQL service.
    sqlite_db_path = os.path.join(instance_path, 'sattest.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + sqlite_db_path
    app.logger.info(f"SQLite path: {sqlite_db_path}")


app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Users will be redirected here if not logged in
login_manager.login_message_category = "warning" # For flash messages

# --- Database Models (User, Score) ---
# (Keep your existing User and Score models here)
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    scores = db.relationship('Score', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Score(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    total_score = db.Column(db.Integer, nullable=False)
    math_score = db.Column(db.Integer, nullable=False)
    rw_score = db.Column(db.Integer, nullable=False)
    correct_count = db.Column(db.Integer)
    total_answered = db.Column(db.Integer) # Number of questions the user provided an answer for
    answers_data = db.Column(db.Text, nullable=True) # JSON string of {q_id: user_answer}


@login_manager.user_loader
def load_user(user_id):
    # app.logger.debug(f"Attempting to load user with ID: {user_id}") # Optional debug log
    try:
        user = User.query.get(int(user_id))
        # if not user:
        #     app.logger.warning(f"load_user: No user found for ID {user_id}")
        return user
    except Exception as e:
        app.logger.error(f"Error in load_user for ID {user_id}: {e}", exc_info=True)
        return None


# --- Question Data & Test Logic ---
# (Keep your QUESTIONS_DATA, ALL_QUESTIONS, etc. as previously defined for 30 questions)
# (Ensure calculate_mock_score, initialize_test_session, generate_csv_report are correct)
QUESTIONS_DATA = {
    "math": [
        {"id": "m1", "module": 1, "text": "If 5x + 6 = 10, what is the value of 5x + 3?", "options": ["1", "3", "4", "7"], "correctAnswer": "7", "topic": "Algebra", "difficulty": "Easy"},
        # ... (10 math questions) ...
        {"id": "m10", "module": 1, "text": "A survey of 50 students found that 30 like apples and 25 like bananas. If 10 students like both, how many students like neither?", "options": ["0", "5", "10", "15"], "correctAnswer": "5", "topic": "Problem-Solving and Data Analysis (Sets)", "difficulty": "Hard"}
    ],
    "reading_writing": [
        {"id": "rw1", "module": 1, "passage": "The following is an excerpt...", "text": "What is Sarah's profession?", "options": ["Ghost hunter", "Historian", "Journalist", "Librarian"], "correctAnswer": "Journalist", "topic": "Information and Ideas", "difficulty": "Easy"},
        # ... (19 more R&W questions to make 20 total) ...
        {"id": "rw20", "module": 1, "text": "The word 'ubiquitous' means:", "options": ["Rare", "Everywhere", "Expensive", "Temporary"], "correctAnswer": "Everywhere", "topic": "Vocabulary", "difficulty": "Hard"}
    ]
}
ALL_QUESTIONS = QUESTIONS_DATA["math"] + QUESTIONS_DATA["reading_writing"]
ALL_QUESTIONS_MAP = {q['id']: q for q in ALL_QUESTIONS}
ORDERED_QUESTION_IDS = [q['id'] for q in ALL_QUESTIONS]

TOTAL_QUESTIONS = len(ALL_QUESTIONS)
TEST_DURATION_MINUTES = 30 # Or adjust as needed for 30 questions

def initialize_test_session():
    app.logger.info(f"Initializing test session for user: {current_user.id if current_user.is_authenticated else 'Anonymous'}")
    session['current_question_index'] = 0
    session['answers'] = {}
    session['start_time'] = datetime.datetime.now().isoformat()
    session['test_questions_ids_ordered'] = ORDERED_QUESTION_IDS[:]
    session['marked_for_review'] = {}
    session.modified = True

def calculate_mock_score(answers):
    # ... (Your existing calculate_mock_score logic, ensure it handles cases like division by zero if no questions in a section)
    correct_count = 0
    math_correct = 0
    math_total_qs_in_test = sum(1 for q_id in ORDERED_QUESTION_IDS if q_id.startswith('m'))
    rw_total_qs_in_test = sum(1 for q_id in ORDERED_QUESTION_IDS if q_id.startswith('rw'))

    for q_id, user_answer in answers.items():
        question_detail = ALL_QUESTIONS_MAP.get(q_id)
        if not question_detail: continue
        
        is_math = q_id.startswith('m') # Assuming 'm' prefix for math, 'rw' for reading/writing
        
        if user_answer == question_detail['correctAnswer']:
            correct_count += 1
            if is_math: math_correct += 1
            # else: rw_correct handled by total correct - math_correct if needed, or track explicitly

    rw_correct = correct_count - math_correct # Calculate R&W correct

    mock_math_score = 200 + int((math_correct / max(1, math_total_qs_in_test)) * 600) if math_total_qs_in_test > 0 else 200
    mock_rw_score = 200 + int((rw_correct / max(1, rw_total_qs_in_test)) * 600) if rw_total_qs_in_test > 0 else 200
    
    mock_total_score = mock_math_score + mock_rw_score
    
    mock_math_score = max(200, min(800, mock_math_score))
    mock_rw_score = max(200, min(800, mock_rw_score))
    mock_total_score = max(400, min(1600, mock_total_score))
    
    # ... (rest of weaknesses/recommendations logic) ...
    weaknesses = []
    recommendations = []
    if math_total_qs_in_test > 0 and (math_correct / math_total_qs_in_test) < 0.6:
        weaknesses.append("Math Concepts")
        recommendations.append("Review foundational math topics.")
    if rw_total_qs_in_test > 0 and (rw_correct / rw_total_qs_in_test) < 0.6:
        weaknesses.append("Reading & Writing Skills")
        recommendations.append("Focus on grammar and passage analysis.")
    if not weaknesses:
        weaknesses.append("Good overall performance!")
        recommendations.append("Explore advanced topics.")

    return {
        "total_score": mock_total_score, "math_score": mock_math_score, "rw_score": mock_rw_score,
        "correct_count": correct_count, "total_answered": len(answers),
        "total_test_questions": TOTAL_QUESTIONS,
        "weaknesses": weaknesses, "recommendations": recommendations
    }


# --- Routes ---
@app.route('/')
def index():
    app.logger.info(f"Index page accessed by user: {current_user.id if current_user.is_authenticated else 'Anonymous'}")
    return render_template('index.html', total_questions=TOTAL_QUESTIONS, duration=TEST_DURATION_MINUTES, now=datetime.datetime.utcnow())

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        app.logger.info(f"Registration attempt for username: {username}")
        # ... (rest of your registration logic)
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose a different one.', 'danger')
            return redirect(url_for('register'))
        if not username or not password: # Basic validation
            flash('Username and password are required.', 'warning')
            return redirect(url_for('register'))
        
        new_user = User(username=username)
        new_user.set_password(password)
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful! Please log in.', 'success')
            app.logger.info(f"User {username} registered successfully.")
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error during registration for {username}: {e}", exc_info=True)
            flash('An error occurred during registration. Please try again.', 'danger')
            return redirect(url_for('register'))
    return render_template('register.html', now=datetime.datetime.utcnow())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        app.logger.info(f"Login attempt for username: {username}")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=request.form.get('remember') == 'on')
            flash('Logged in successfully!', 'success')
            app.logger.info(f"User {username} logged in successfully.")
            next_page = request.args.get('next')
            # Security: Validate next_page if it's from user input to prevent open redirect
            if next_page and not (next_page.startswith('/') or next_page.startswith(request.host_url)):
                app.logger.warning(f"Invalid next_page URL in login: {next_page}")
                next_page = None # Or url_for('index')
            return redirect(next_page or url_for('index'))
        else:
            flash('Invalid username or password.', 'danger')
            app.logger.warning(f"Failed login attempt for username: {username}")
    return render_template('login.html', now=datetime.datetime.utcnow())

@app.route('/logout')
@login_required
def logout():
    app.logger.info(f"User {current_user.username} logging out.")
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard/')
@login_required
def dashboard():
    app.logger.info(f"Dashboard accessed by user: {current_user.username}")
    try:
        user_scores = Score.query.filter_by(user_id=current_user.id).order_by(Score.timestamp.desc()).all()
    except Exception as e:
        app.logger.error(f"Error fetching scores for dashboard for user {current_user.username}: {e}", exc_info=True)
        flash("Could not load scores. Please try again later.", "danger")
        user_scores = []
    return render_template('dashboard.html', scores=user_scores, now=datetime.datetime.utcnow())

@app.route('/start_test', methods=['POST'])
@login_required
def start_test():
    app.logger.info(f"User {current_user.username} starting test.")
    initialize_test_session()
    return redirect(url_for('test_question_page', q_idx=0))

@app.route('/test/question/<int:q_idx>', methods=['GET', 'POST'])
@login_required
def test_question_page(q_idx):
    # app.logger.debug(f"Test question page {q_idx} accessed by {current_user.username}. Method: {request.method}")
    if 'test_questions_ids_ordered' not in session or not session['test_questions_ids_ordered']:
        flash('Test session not found or expired. Please start a new test.', 'warning')
        app.logger.warning(f"Test session not found for {current_user.username} accessing q_idx {q_idx}.")
        return redirect(url_for('index'))

    ordered_ids = session['test_questions_ids_ordered']
    
    if not (0 <= q_idx < len(ordered_ids)):
        current_q_idx_in_session = session.get('current_question_index', 0)
        flash('Invalid question number.', 'danger')
        app.logger.warning(f"Invalid q_idx {q_idx} for {current_user.username}. Max is {len(ordered_ids)-1}. Redirecting to {current_q_idx_in_session}.")
        # Ensure redirect target is valid
        if not (0 <= current_q_idx_in_session < len(ordered_ids)):
            return redirect(url_for('index')) # Fallback if session index is also bad
        return redirect(url_for('test_question_page', q_idx=current_q_idx_in_session))

    session['current_question_index'] = q_idx
    question_id = ordered_ids[q_idx]
    question = ALL_QUESTIONS_MAP.get(question_id)

    if not question:
        flash('Error: Question not found.', 'danger')
        app.logger.error(f"Question ID {question_id} not found in ALL_QUESTIONS_MAP for user {current_user.username}.")
        return redirect(url_for('index'))

    if request.method == 'POST':
        # app.logger.debug(f"POST request for q_idx {q_idx}, question_id {question_id} by {current_user.username}. Form: {request.form}")
        selected_option = request.form.get('answer')
        if selected_option:
            session.setdefault('answers', {})[question_id] = selected_option
        
        if 'mark_review' in request.form: # Checkbox sends 'true' if checked
            session.setdefault('marked_for_review', {})[question_id] = True
        elif question_id in session.get('marked_for_review', {}): # Unchecked and was previously marked
             # Only remove if checkbox was present in form but not checked.
             # Browsers don't send unchecked checkboxes. So if 'mark_review' is NOT in request.form, it means it was unchecked or not present.
             # This logic is tricky with direct form submit on checkbox change.
             # A hidden field with value 'false' for mark_review that is overridden by checkbox value 'true' is more robust.
             # For now, if 'mark_review' is not in form, assume it was unchecked (if it was in session).
            if 'mark_review' not in request.form: # Checkbox was unchecked
                 session.get('marked_for_review', {}).pop(question_id, None)
        
        session.modified = True

        action = request.form.get('action') # For 'Next'/'Back' buttons
        if action == 'next':
            if q_idx + 1 < len(ordered_ids):
                return redirect(url_for('test_question_page', q_idx=q_idx + 1))
            else:
                return redirect(url_for('results'))
        elif action == 'back':
            if q_idx > 0:
                return redirect(url_for('test_question_page', q_idx=q_idx - 1))
        # If action is not 'next' or 'back' (e.g. direct submit from mark_review checkbox)
        return redirect(url_for('test_question_page', q_idx=q_idx))

    # GET request logic
    current_section_name = "Math" if question_id.startswith('m') else "Reading & Writing"
    current_module = question.get('module', 1)
    is_marked = session.get('marked_for_review', {}).get(question_id, False)
    selected_answer = session.get('answers', {}).get(question_id)
    
    return render_template('test_page.html', 
                           question=question, 
                           question_number=q_idx + 1, 
                           total_questions=TOTAL_QUESTIONS,
                           current_section=f"Section {1 if current_section_name == 'Math' else 2}, Module {current_module}: {current_section_name}",
                           start_time_iso=session['start_time'], 
                           test_duration_minutes=TEST_DURATION_MINUTES,
                           now=datetime.datetime.utcnow(), 
                           is_marked_for_review=is_marked,
                           selected_answer=selected_answer, 
                           q_idx=q_idx)


@app.route('/results')
@login_required
def results():
    app.logger.info(f"Results page accessed by {current_user.username}.")
    if 'answers' not in session or 'start_time' not in session:
        flash('No answers recorded or session expired. Please start a new test.', 'warning')
        app.logger.warning(f"Results page: No answers or start_time in session for {current_user.username}.")
        return redirect(url_for('index'))

    user_submitted_answers = session.get('answers', {})
    start_time = datetime.datetime.fromisoformat(session['start_time'])
    end_time = datetime.datetime.now()
    time_taken_seconds = (end_time - start_time).total_seconds()
    
    results_summary = calculate_mock_score(user_submitted_answers)
    results_summary['time_taken_formatted'] = f"{int(time_taken_seconds // 60)}m {int(time_taken_seconds % 60)}s"
    
    answers_json_string = json.dumps(user_submitted_answers)
    
    try:
        new_score = Score(user_id=current_user.id,
                          total_score=results_summary['total_score'],
                          math_score=results_summary['math_score'],
                          rw_score=results_summary['rw_score'],
                          correct_count=results_summary['correct_count'],
                          total_answered=results_summary['total_answered'],
                          answers_data=answers_json_string,
                          timestamp=end_time)
        db.session.add(new_score)
        db.session.commit()
        app.logger.info(f"Score saved for user {current_user.username}, score ID: {new_score.id}")
        score_id_for_template = new_score.id
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error saving score for {current_user.username}: {e}", exc_info=True)
        flash("An error occurred while saving your score. Please try again.", "danger")
        score_id_for_template = None # Or handle differently

    # Clean up test session data
    session_keys_to_pop = ['current_question_index', 'answers', 'start_time', 'test_questions_ids_ordered', 'marked_for_review']
    for key in session_keys_to_pop:
        session.pop(key, None)
    session.modified = True
        
    flash('Your test results have been saved!', 'success')
    return render_template('results_page.html', results=results_summary, score_id=score_id_for_template, now=datetime.datetime.utcnow())

# ... (keep generate_csv_report, download_report, reset_test, init-db command)
# Make sure generate_csv_report is robust
def generate_csv_report(score_obj):
    # ... (your existing robust CSV generation) ...
    output = io.StringIO()
    writer = csv.writer(output)
    # ... headers ...
    # ... data rows ...
    return output.getvalue()


@app.route('/download_report/<int:score_id>/<string:report_format>')
@login_required
def download_report(score_id, report_format):
    score_to_download = db.session.get(Score, score_id) # Use new db.session.get for Flask-SQLAlchemy 3+
    if not score_to_download or score_to_download.user_id != current_user.id:
        flash("Score not found or access denied.", "danger")
        return redirect(request.referrer or url_for('dashboard'))

    if report_format == 'csv':
        csv_data = generate_csv_report(score_to_download)
        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename=sat_detailed_report_{score_id}.csv"}
        )
    else:
        flash("Invalid or unsupported report format requested.", "danger")
        return redirect(request.referrer or url_for('dashboard'))


@app.route('/reset_test', methods=['POST'])
@login_required
def reset_test():
    session_keys_to_pop = ['current_question_index', 'answers', 'start_time', 'test_questions_ids_ordered', 'marked_for_review']
    for key in session_keys_to_pop:
        session.pop(key, None)
    session.modified = True
    flash('Test session reset. You can start a new test.', 'info')
    return redirect(url_for('index'))

@app.cli.command("init-db")
def init_db_command():
    """Creates the database tables."""
    try:
        with app.app_context():
            db.create_all()
        print("Initialized the database.")
    except Exception as e:
        print(f"Error initializing database: {e}")
        # Potentially log to app.logger as well if it's configured early enough
        # app.logger.error(f"Error initializing database via CLI: {e}", exc_info=True)


# --- Main Gunicorn Entry Point for Render ---
# Render will typically use a Procfile like: web: gunicorn app:app
# The 'if __name__ == '__main__':' block is for local Flask development server.
if __name__ == '__main__':
    app.logger.info("Starting Flask development server.")
    # For local development, consider creating tables if they don't exist,
    # but init-db command is preferred for explicit control.
    # with app.app_context():
    #     db.create_all() # This might try to create tables every time, use init-db
        
    app.run(debug=os.environ.get('FLASK_DEBUG', 'False').lower() == 'true',
            host='0.0.0.0', # Listen on all interfaces
            port=int(os.environ.get('PORT', 5000)))
