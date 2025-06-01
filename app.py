from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
import datetime
import io
import csv
import json
import logging

# --- Application Setup ---
app = Flask(__name__)

# --- Logging Setup ---
is_debug_env = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
log_level = logging.DEBUG if is_debug_env else logging.INFO
app.logger.setLevel(log_level)
if is_debug_env:
    logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s %(name)s : %(message)s')
    app.logger.info('SATInsight App Starting Up in DEBUG mode')
else:
    app.logger.info('SATInsight App Starting Up in Production-like mode')

# --- SECRET_KEY Configuration ---
# CRITICAL FOR RENDER: SET THIS IN YOUR RENDER ENVIRONMENT VARIABLES!
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
if not app.config['SECRET_KEY']:
    app.logger.critical("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    app.logger.critical("!!! FATAL ERROR: SECRET_KEY ENVIRONMENT VARIABLE IS NOT SET                 !!!")
    app.logger.critical("!!! Application WILL CRASH on session use (login, flash, test state).     !!!")
    app.logger.critical("!!! SET THIS IN YOUR RENDER SERVICE ENVIRONMENT SETTINGS IMMEDIATELY.     !!!")
    app.logger.critical("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    if is_debug_env:
        app.logger.warning("DEVELOPMENT ONLY: Using an INSECURE temporary SECRET_KEY.")
        app.config['SECRET_KEY'] = "temporary_insecure_dev_secret_key_12345_replace_this"

# --- Database Configuration ---
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    app.logger.info(f"DATABASE_URL detected. Type: {DATABASE_URL.split('://')[0] if '://' in DATABASE_URL else 'Unknown'}")
    if DATABASE_URL.startswith("postgres://"):
        app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
else:
    app.logger.warning("DATABASE_URL NOT FOUND. Defaulting to local SQLite (NOT FOR RENDER PRODUCTION).")
    instance_path = os.path.join(app.instance_path)
    if not os.path.exists(instance_path): os.makedirs(instance_path, exist_ok=True)
    sqlite_db_file = os.path.join(instance_path, 'sattest.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + sqlite_db_file
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = 'info'

# --- Database Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    scores = db.relationship('Score', backref='user', lazy='dynamic')
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class Score(db.Model):
    id = db.Column(db.Integer, primary_key=True); user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow); total_score = db.Column(db.Integer, nullable=False)
    math_score = db.Column(db.Integer, nullable=False); rw_score = db.Column(db.Integer, nullable=False)
    correct_count = db.Column(db.Integer); total_answered = db.Column(db.Integer); answers_data = db.Column(db.Text, nullable=True)

@login_manager.user_loader
def load_user(user_id_str):
    try: user = db.session.get(User, int(user_id_str))
    except Exception as e: app.logger.error(f"load_user error for '{user_id_str}': {e}"); return None
    return user

# --- Question Data (Ensure 10 math + 20 R&W for 30 total) ---
QUESTIONS_DATA = {
    "math": [ # 10 Math Questions
        {"id": "m1", "module": 1, "text": "If 5x + 6 = 10, what is the value of 5x + 3?", "options": ["1", "3", "4", "7"], "correctAnswer": "7", "topic": "Algebra", "difficulty": "Easy"},
        {"id": "m2", "module": 1, "text": "A rectangular garden is 10 feet long and 5 feet wide. What is its area in square feet?", "options": ["15", "25", "50", "100"], "correctAnswer": "50", "topic": "Geometry", "difficulty": "Easy"},
        {"id": "m3", "module": 1, "text": "What is 20% of 200?", "options": ["20", "40", "50", "100"], "correctAnswer": "40", "topic": "Problem-Solving", "difficulty": "Easy"},
        {"id": "m4", "module": 1, "text": "If a circle has radius 3, circumference? (π ≈ 3.14)", "options": ["9.42", "18.84", "28.26", "6.00"], "correctAnswer": "18.84", "topic": "Geometry", "difficulty": "Medium"},
        {"id": "m5", "module": 1, "text": "Solve for y: 3(y - 2) = 9", "options": ["3", "4", "5", "6"], "correctAnswer": "5", "topic": "Algebra", "difficulty": "Medium"},
        {"id": "m6", "module": 1, "text": "Car travels 120 miles in 2 hours. Avg speed?", "options": ["50", "60", "70", "80"], "correctAnswer": "60", "topic": "Problem-Solving", "difficulty": "Easy"},
        {"id": "m7", "module": 1, "text": "Next number: 2, 5, 8, 11, ...?", "options": ["12", "13", "14", "15"], "correctAnswer": "14", "topic": "Algebra", "difficulty": "Easy"},
        {"id": "m8", "module": 1, "text": "Triangle angles 45°, 45°, x°. Value of x?", "options": ["45°", "60°", "90°", "100°"], "correctAnswer": "90°", "topic": "Geometry", "difficulty": "Medium"},
        {"id": "m9", "module": 1, "text": "Simplify: (2^3) * (2^2)", "options": ["2^1", "2^5", "2^6", "4^5"], "correctAnswer": "2^5", "topic": "Algebra", "difficulty": "Medium"},
        {"id": "m10", "module": 1, "text": "Survey: 50 students, 30 apples, 25 bananas, 10 both. How many neither?", "options": ["0", "5", "10", "15"], "correctAnswer": "5", "topic": "Sets", "difficulty": "Hard"}
    ],
    "reading_writing": [ # 20 Reading & Writing Questions (replace placeholders with actual questions)
        {"id": "rw1", "module": 1, "passage": "The old house stood on a hill...", "text": "What is Sarah's profession?", "options": ["Ghost hunter", "Historian", "Journalist", "Librarian"], "correctAnswer": "Journalist", "topic": "Information and Ideas", "difficulty": "Easy"},
        {"id": "rw2", "module": 1, "text": "Placeholder R&W Question 2 Text", "options": ["OptA2", "OptB2", "OptC2", "OptD2"], "correctAnswer": "OptA2", "topic": "Topic 2", "difficulty": "Easy"},
        {"id": "rw3", "module": 1, "text": "Placeholder R&W Question 3 Text", "options": ["OptA3", "OptB3", "OptC3", "OptD3"], "correctAnswer": "OptB3", "topic": "Topic 3", "difficulty": "Medium"},
        {"id": "rw4", "module": 1, "passage": "Passage for Q4...", "text": "Placeholder R&W Question 4 Text", "options": ["OptA4", "OptB4", "OptC4", "OptD4"], "correctAnswer": "OptC4", "topic": "Topic 4", "difficulty": "Medium"},
        {"id": "rw5", "module": 1, "text": "Placeholder R&W Question 5 Text", "options": ["OptA5", "OptB5", "OptC5", "OptD5"], "correctAnswer": "OptD5", "topic": "Topic 5", "difficulty": "Easy"},
        {"id": "rw6", "module": 1, "text": "Placeholder R&W Question 6 Text", "options": ["OptA6", "OptB6", "OptC6", "OptD6"], "correctAnswer": "OptA6", "topic": "Topic 6", "difficulty": "Hard"},
        {"id": "rw7", "module": 1, "passage": "Passage for Q7...", "text": "Placeholder R&W Question 7 Text", "options": ["OptA7", "OptB7", "OptC7", "OptD7"], "correctAnswer": "OptB7", "topic": "Topic 7", "difficulty": "Easy"},
        {"id": "rw8", "module": 1, "text": "Placeholder R&W Question 8 Text", "options": ["OptA8", "OptB8", "OptC8", "OptD8"], "correctAnswer": "OptC8", "topic": "Topic 8", "difficulty": "Medium"},
        {"id": "rw9", "module": 1, "text": "Placeholder R&W Question 9 Text", "options": ["OptA9", "OptB9", "OptC9", "OptD9"], "correctAnswer": "OptD9", "topic": "Topic 9", "difficulty": "Medium"},
        {"id": "rw10", "module": 1, "text": "Placeholder R&W Question 10 Text", "options": ["OptA10", "OptB10", "OptC10", "OptD10"], "correctAnswer": "OptA10", "topic": "Topic 10", "difficulty": "Hard"},
        {"id": "rw11", "module": 1, "passage": "Passage for Q11...", "text": "Placeholder R&W Question 11 Text", "options": ["OptA11", "OptB11", "OptC11", "OptD11"], "correctAnswer": "OptB11", "topic": "Topic 11", "difficulty": "Medium"},
        {"id": "rw12", "module": 1, "text": "Placeholder R&W Question 12 Text", "options": ["OptA12", "OptB12", "OptC12", "OptD12"], "correctAnswer": "OptC12", "topic": "Topic 12", "difficulty": "Hard"},
        {"id": "rw13", "module": 1, "text": "Placeholder R&W Question 13 Text", "options": ["OptA13", "OptB13", "OptC13", "OptD13"], "correctAnswer": "OptD13", "topic": "Topic 13", "difficulty": "Medium"},
        {"id": "rw14", "module": 1, "text": "Placeholder R&W Question 14 Text", "options": ["OptA14", "OptB14", "OptC14", "OptD14"], "correctAnswer": "OptA14", "topic": "Topic 14", "difficulty": "Easy"},
        {"id": "rw15", "module": 1, "passage": "Passage for Q15...", "text": "Placeholder R&W Question 15 Text", "options": ["OptA15", "OptB15", "OptC15", "OptD15"], "correctAnswer": "OptB15", "topic": "Topic 15", "difficulty": "Medium"},
        {"id": "rw16", "module": 1, "text": "Placeholder R&W Question 16 Text", "options": ["OptA16", "OptB16", "OptC16", "OptD16"], "correctAnswer": "OptC16", "topic": "Topic 16", "difficulty": "Hard"},
        {"id": "rw17", "module": 1, "text": "Placeholder R&W Question 17 Text", "options": ["OptA17", "OptB17", "OptC17", "OptD17"], "correctAnswer": "OptD17", "topic": "Topic 17", "difficulty": "Easy"},
        {"id": "rw18", "module": 1, "text": "Placeholder R&W Question 18 Text", "options": ["OptA18", "OptB18", "OptC18", "OptD18"], "correctAnswer": "OptA18", "topic": "Topic 18", "difficulty": "Medium"},
        {"id": "rw19", "module": 1, "passage": "Passage for Q19...", "text": "Placeholder R&W Question 19 Text", "options": ["OptA19", "OptB19", "OptC19", "OptD19"], "correctAnswer": "OptB19", "topic": "Topic 19", "difficulty": "Medium"},
        {"id": "rw20", "module": 1, "text": "The word 'ubiquitous' means:", "options": ["Rare and hard to find", "Present, appearing, or found everywhere", "Expensive and luxurious", "Temporary and fleeting"], "correctAnswer": "Present, appearing, or found everywhere", "topic": "Craft and Structure (Vocabulary)", "difficulty": "Hard"}
    ]
}
ALL_QUESTIONS = QUESTIONS_DATA["math"] + QUESTIONS_DATA["reading_writing"]
ALL_QUESTIONS_MAP = {q['id']: q for q in ALL_QUESTIONS}
ORDERED_QUESTION_IDS = [q['id'] for q in ALL_QUESTIONS]
TOTAL_QUESTIONS = len(ALL_QUESTIONS)
TEST_DURATION_MINUTES = 30
app.logger.info(f"Successfully loaded {TOTAL_QUESTIONS} questions ({len(QUESTIONS_DATA['math'])} Math, {len(QUESTIONS_DATA['reading_writing'])} R&W).")

def initialize_test_session():
    user_id_log = current_user.id if current_user.is_authenticated else 'Anonymous (User not authenticated during session init)'
    app.logger.info(f"Attempting to initialize test session for user: {user_id_log}")
    keys_to_pop = ['current_question_index', 'answers', 'start_time', 'test_questions_ids_ordered', 'marked_for_review']
    for key in keys_to_pop: session.pop(key, None)
    session['current_question_index'] = 0
    session['answers'] = {}
    session['start_time'] = datetime.datetime.now().isoformat()
    if not ORDERED_QUESTION_IDS:
        app.logger.error("CRITICAL FAILURE: ORDERED_QUESTION_IDS is empty during session init! No questions loaded.")
        raise ValueError("Cannot start test: No questions are available. Check server configuration.")
    session['test_questions_ids_ordered'] = ORDERED_QUESTION_IDS[:]
    session['marked_for_review'] = {}
    session.modified = True
    app.logger.info(f"Session successfully initialized for test for user {user_id_log}. "
                    f"Start time: {session.get('start_time')}, "
                    f"Num Qs ordered: {len(session.get('test_questions_ids_ordered', []))}. "
                    f"Current session keys: {sorted(list(session.keys()))}")

def calculate_mock_score(answers):
    # ... (Keep this function as provided in the previous detailed answer) ...
    correct_count = 0; math_correct = 0; rw_correct = 0
    math_total_qs_in_test = sum(1 for q_id in ORDERED_QUESTION_IDS if q_id.startswith('m'))
    rw_total_qs_in_test = sum(1 for q_id in ORDERED_QUESTION_IDS if q_id.startswith('rw'))
    for q_id, user_answer in answers.items():
        question_detail = ALL_QUESTIONS_MAP.get(q_id);
        if not question_detail: continue
        is_math = q_id.startswith('m')
        if user_answer == question_detail['correctAnswer']:
            correct_count += 1
            if is_math: math_correct += 1
            else: rw_correct += 1
    mock_math_score = 200 + int((math_correct / max(1, math_total_qs_in_test)) * 600) if math_total_qs_in_test > 0 else 200
    mock_rw_score = 200 + int((rw_correct / max(1, rw_total_qs_in_test)) * 600) if rw_total_qs_in_test > 0 else 200
    mock_total_score = mock_math_score + mock_rw_score
    mock_math_score = max(200, min(800, mock_math_score)); mock_rw_score = max(200, min(800, mock_rw_score)); mock_total_score = max(400, min(1600, mock_total_score))
    weaknesses = []; recommendations = []
    if TOTAL_QUESTIONS > 0:
        if math_total_qs_in_test > 0 and (math_correct / math_total_qs_in_test) < 0.6: weaknesses.append("Math Concepts"); recommendations.append("Review math topics.")
        if rw_total_qs_in_test > 0 and (rw_correct / rw_total_qs_in_test) < 0.6: weaknesses.append("R&W Skills"); recommendations.append("Focus on R&W techniques.")
        if not weaknesses: weaknesses.append("Good performance!"); recommendations.append("Keep practicing.")
    else: weaknesses.append("No questions."); recommendations.append("Check config.")
    return {"total_score": mock_total_score, "math_score": mock_math_score, "rw_score": mock_rw_score, "correct_count": correct_count, "total_answered": len(answers), "total_test_questions": TOTAL_QUESTIONS, "weaknesses": weaknesses, "recommendations": recommendations}


def generate_csv_report(score_obj):
    # ... (Keep this function as provided in the previous detailed answer) ...
    output = io.StringIO(); writer = csv.writer(output)
    headers = ["Question Number", "Section", "Skill Type", "Your Answer", "Correct Answer", "Outcome", "QuestionID", "Module", "Difficulty", "QuestionText", "AllOptions", "ScoreID", "TestDate"]
    writer.writerow(headers)
    if not score_obj or not score_obj.answers_data: writer.writerow(["N/A"] * len(headers[:-2]) + [score_obj.id if score_obj else "N/A", "N/A"]); output.seek(0); return output.getvalue()
    try: user_answers_dict = json.loads(score_obj.answers_data)
    except json.JSONDecodeError: writer.writerow(["Error decoding answers"] + ["N/A"] * (len(headers) - 3) + [score_obj.id, score_obj.timestamp.strftime('%Y-%m-%d %H:%M:%S') if score_obj.timestamp else "N/A"]); output.seek(0); return output.getvalue()
    test_date_str = score_obj.timestamp.strftime('%Y-%m-%d %H:%M:%S') if score_obj.timestamp else "N/A"
    for idx, q_id in enumerate(ORDERED_QUESTION_IDS):
        question_detail = ALL_QUESTIONS_MAP.get(q_id); question_sequence_number = idx + 1
        if not question_detail: writer.writerow([question_sequence_number, "Unknown", "N/A", "N/A", "N/A", "Question Detail Missing", q_id, "N/A", "N/A", f"Details missing: {q_id}", "[]", score_obj.id, test_date_str]); continue
        section_val = "Math" if q_id.startswith('m') else "Reading & Writing"; skill_type_val = question_detail.get("topic", "N/A"); user_answer_val = user_answers_dict.get(q_id, "Not Answered"); correct_answer_val = question_detail.get("correctAnswer", "N/A")
        outcome_val = "Not Answered";
        if user_answer_val != "Not Answered": outcome_val = "Correct" if user_answer_val == correct_answer_val else "Incorrect"
        module_val = question_detail.get("module", "N/A"); difficulty_val = question_detail.get("difficulty", "N/A"); question_text_val = question_detail.get("text", "N/A")
        if question_detail.get("passage"): question_text_val = f"[Passage Based] {question_text_val}"
        all_options_json = json.dumps(question_detail.get("options", []))
        writer.writerow([question_sequence_number, section_val, skill_type_val, user_answer_val, correct_answer_val, outcome_val, q_id, module_val, difficulty_val, question_text_val, all_options_json, score_obj.id, test_date_str])
    output.seek(0)
    return output.getvalue()

# --- Error Handlers ---
@app.errorhandler(404)
def page_not_found_error_handler(e):
    user_id_log = current_user.id if current_user.is_authenticated else 'Anonymous'
    app.logger.warning(f"404 Not Found: {request.url} (Referrer: {request.referrer}) by user {user_id_log}")
    return render_template('error_page.html', error_code=404, error_name="Page Not Found", error_message="The page you were looking for doesn't exist."), 404

@app.errorhandler(Exception)
def handle_general_exception_handler(e):
    app.logger.error(f"Unhandled application exception: {e} at {request.url}", exc_info=True)
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return render_template("error_page.html", error_code=e.code, error_name=e.name, error_message=e.description), e.code
    return render_template("error_page.html", error_code=500, error_name="Internal Server Error", error_message="An unexpected internal error occurred. We've been notified."), 500

# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html', total_questions=TOTAL_QUESTIONS, duration=TEST_DURATION_MINUTES, now=datetime.datetime.utcnow())

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username','').strip(); password = request.form.get('password')
        if not username or not password: flash('Username and password are required.', 'warning'); return redirect(url_for('register'))
        if len(username) < 3: flash('Username must be >= 3 chars.', 'warning'); return redirect(url_for('register'))
        if len(password) < 6: flash('Password must be >= 6 chars.', 'warning'); return redirect(url_for('register'))
        if User.query.filter_by(username=username).first(): flash('Username already exists.', 'danger'); return redirect(url_for('register'))
        new_user = User(username=username); new_user.set_password(password)
        try: db.session.add(new_user); db.session.commit(); flash('Registration successful! Please log in.', 'success'); return redirect(url_for('login'))
        except Exception as e: db.session.rollback(); app.logger.error(f"DB error on register: {e}", exc_info=True); flash('DB error during registration.', 'danger'); return redirect(url_for('register'))
    return render_template('register.html', now=datetime.datetime.utcnow())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username','').strip(); password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=(request.form.get('remember') == 'on'))
            flash('Logged in successfully!', 'success');
            app.logger.info(f"User '{username}' logged in.")
            next_page = request.args.get('next')
            if next_page and not (next_page.startswith('/') or next_page.startswith(request.host_url)):
                 app.logger.warning(f"Invalid 'next' URL '{next_page}' during login. Defaulting to index."); next_page = url_for('index')
            return redirect(next_page or url_for('index'))
        else: flash('Invalid username or password.', 'danger')
    return render_template('login.html', now=datetime.datetime.utcnow())

@app.route('/logout')
@login_required
def logout():
    user_id_log = current_user.username
    logout_user()
    session.clear() # Clear the entire session
    flash('You have been successfully logged out.', 'info')
    app.logger.info(f"User '{user_id_log}' logged out and session cleared.")
    return redirect(url_for('index'))

@app.route('/dashboard/')
@login_required
def dashboard():
    try: user_scores = current_user.scores.order_by(Score.timestamp.desc()).all()
    except Exception as e: app.logger.error(f"DB error on dashboard for '{current_user.username}': {e}", exc_info=True); flash('Could not load scores.', 'danger'); user_scores = []
    return render_template('dashboard.html', scores=user_scores, now=datetime.datetime.utcnow())


@app.route('/start_test', methods=['POST'])
@login_required
def start_test():
    user_id_log = current_user.username
    app.logger.info(f"User '{user_id_log}' is POSTing to /start_test.")
    try:
        initialize_test_session()
        app.logger.info(f"Test session successfully initialized for '{user_id_log}'. Redirecting to first question (q_idx=0).")
        return redirect(url_for('test_question_page', q_idx=0))
    except ValueError as ve: # Catch specific error from initialize_test_session if no questions
        app.logger.error(f"ValueError during start_test for user '{user_id_log}': {ve}", exc_info=True)
        flash(str(ve), "danger")
        return redirect(url_for('index'))
    except Exception as e:
        app.logger.error(f"Generic error during start_test for user '{user_id_log}': {e}", exc_info=True)
        flash("An unexpected server error occurred while trying to start the test. Please try again.", "danger")
        return redirect(url_for('index'))

@app.route('/test/question/<int:q_idx>', methods=['GET', 'POST'])
@login_required
def test_question_page(q_idx):
    user_id_log = current_user.username
    app.logger.info(f"Accessing /test/question/{q_idx} for user '{user_id_log}'. Method: {request.method}.")
    app.logger.debug(f"Session keys for '{user_id_log}' at q_idx {q_idx}: {sorted(list(session.keys()))}")
    app.logger.debug(f"Session 'test_questions_ids_ordered' length: {len(session.get('test_questions_ids_ordered', []))}, 'start_time': {session.get('start_time')}")

    required_session_keys = ['test_questions_ids_ordered', 'answers', 'start_time', 'marked_for_review', 'current_question_index']
    session_valid = True
    missing_keys = [key for key in required_session_keys if key not in session]

    if missing_keys:
        session_valid = False
        app.logger.error(f"SESSION INVALID for '{user_id_log}' at q_idx {q_idx}. Missing session keys: {missing_keys}. Session content: {dict(session)}")
    
    if session_valid and not session.get('test_questions_ids_ordered'): # Also checks if the list itself is empty
        session_valid = False
        app.logger.error(f"SESSION INVALID for '{user_id_log}' at q_idx {q_idx}. 'test_questions_ids_ordered' is empty/None. Session content: {dict(session)}")

    if not session_valid:
        flash('Your test session is invalid or appears to have expired. Please start a new test to continue.', 'warning')
        return redirect(url_for('index'))

    ordered_ids = session['test_questions_ids_ordered']
    if not (0 <= q_idx < len(ordered_ids)):
        valid_q_idx = session.get('current_question_index', 0)
        if not (0 <= valid_q_idx < len(ordered_ids)): valid_q_idx = 0 # Default to first if stored is also bad
        flash('Invalid question number. Redirecting.', 'danger')
        app.logger.warning(f"Out-of-bounds q_idx {q_idx} (max: {len(ordered_ids)-1}) for user '{user_id_log}'. Redirecting to {valid_q_idx}.")
        return redirect(url_for('test_question_page', q_idx=valid_q_idx))
    
    session['current_question_index'] = q_idx
    question_id = ordered_ids[q_idx]
    question = ALL_QUESTIONS_MAP.get(question_id)

    if not question:
        flash('Error: Question data could not be loaded. Please restart the test.', 'danger')
        app.logger.error(f"Question ID '{question_id}' (index {q_idx}) NOT FOUND in ALL_QUESTIONS_MAP for '{user_id_log}'.")
        initialize_test_session() 
        return redirect(url_for('index'))

    if request.method == 'POST':
        # ... (POST logic as previously corrected)
        if request.form.get('answer'): session['answers'][question_id] = request.form.get('answer')
        if 'mark_review' in request.form and request.form.get('mark_review') == 'true':
            session['marked_for_review'][question_id] = True
        else:
            session['marked_for_review'].pop(question_id, None)
        session.modified = True
        action = request.form.get('action')
        if action == 'next':
            if q_idx + 1 < len(ordered_ids): return redirect(url_for('test_question_page', q_idx=q_idx + 1))
            else: return redirect(url_for('results'))
        elif action == 'back':
            if q_idx > 0: return redirect(url_for('test_question_page', q_idx=q_idx - 1))
        return redirect(url_for('test_question_page', q_idx=q_idx))

    current_section_name = "Math" if question_id.startswith('m') else "Reading & Writing"
    current_module = question.get('module', 1)
    is_marked = session.get('marked_for_review', {}).get(question_id, False)
    selected_answer = session.get('answers', {}).get(question_id)
    
    return render_template('test_page.html', 
                           question=question, question_number=q_idx + 1, total_questions=TOTAL_QUESTIONS,
                           current_section=f"Section {1 if current_section_name == 'Math' else 2}, Module {current_module}: {current_section_name}",
                           start_time_iso=session['start_time'], test_duration_minutes=TEST_DURATION_MINUTES,
                           now=datetime.datetime.utcnow(), is_marked_for_review=is_marked,
                           selected_answer=selected_answer, q_idx=q_idx)

@app.route('/results')
@login_required
def results():
    # ... (Keep robust results logic from previous corrected version) ...
    if 'answers' not in session or 'start_time' not in session: flash('Test data incomplete. Start new test.', 'warning'); return redirect(url_for('index'))
    user_submitted_answers = session.get('answers', {}); start_time_iso = session.get('start_time')
    if not start_time_iso: flash('Error: Test start time missing.', 'danger'); return redirect(url_for('index'))
    try: start_time = datetime.datetime.fromisoformat(start_time_iso)
    except: flash('Error with test start time.', 'danger'); return redirect(url_for('index'))
    end_time = datetime.datetime.now(datetime.timezone.utc); time_taken_seconds = (end_time - start_time.replace(tzinfo=datetime.timezone.utc if start_time.tzinfo is None else None)).total_seconds()
    results_summary = calculate_mock_score(user_submitted_answers); results_summary['time_taken_formatted'] = f"{int(time_taken_seconds // 60)}m {int(time_taken_seconds % 60)}s"
    answers_json_string = json.dumps(user_submitted_answers); score_id_for_template = None
    try:
        new_score = Score(user_id=current_user.id, total_score=results_summary['total_score'], math_score=results_summary['math_score'], rw_score=results_summary['rw_score'], correct_count=results_summary['correct_count'], total_answered=results_summary['total_answered'], answers_data=answers_json_string, timestamp=end_time)
        db.session.add(new_score); db.session.commit(); score_id_for_template = new_score.id
        flash('Results saved!', 'success')
    except Exception as e:
        db.session.rollback(); app.logger.error(f"DB error saving score: {e}", exc_info=True); flash('Error saving score.', 'danger')
    session_keys_to_pop = ['current_question_index', 'answers', 'start_time', 'test_questions_ids_ordered', 'marked_for_review']
    for key in session_keys_to_pop: session.pop(key, None)
    session.modified = True
    return render_template('results_page.html', results=results_summary, score_id=score_id_for_template, now=datetime.datetime.utcnow())

@app.route('/download_report/<int:score_id>/<string:report_format>')
@login_required
def download_report(score_id, report_format):
    score_to_download = db.session.get(Score, score_id)
    if not score_to_download or score_to_download.user_id != current_user.id: flash("Score report not found or access denied.", "danger"); return redirect(request.referrer or url_for('dashboard'))
    if report_format.lower() == 'csv':
        try:
            csv_data = generate_csv_report(score_to_download)
            return Response(csv_data, mimetype="text/csv", headers={"Content-disposition": f"attachment; filename=sat_detailed_report_{score_id}.csv"})
        except Exception as e: app.logger.error(f"CSV generation error: {e}", exc_info=True); flash("Error generating CSV.", "danger"); return redirect(request.referrer or url_for('dashboard'))
    else: flash(f"Unsupported report format: {report_format}.", "warning"); return redirect(request.referrer or url_for('dashboard'))

@app.route('/reset_test', methods=['POST'])
@login_required
def reset_test():
    app.logger.info(f"User '{current_user.username}' resetting test.")
    keys_to_pop = ['current_question_index', 'answers', 'start_time', 'test_questions_ids_ordered', 'marked_for_review']
    for key in keys_to_pop: session.pop(key, None)
    session.modified = True
    flash('Test session reset.', 'info'); return redirect(url_for('index'))

@app.cli.command("init-db")
def init_db_command():
    try:
        with app.app_context(): db.create_all()
        app.logger.info("Command 'flask init-db' executed: DB tables checked/created.")
        print("Initialized the database.")
    except Exception as e:
        print(f"Error during 'flask init-db': {e}"); app.logger.error(f"Error in 'flask init-db': {e}", exc_info=True)

# Entry point for Gunicorn on Render (via Procfile: web: gunicorn app:app)
# This __main__ block is for Flask's local development server: python app.py
if __name__ == '__main__':
    app.logger.info(f"Starting Flask development server (Debug: {app.debug}). Listening on http://{os.environ.get('HOST', '0.0.0.0')}:{os.environ.get('PORT', 5000)}")
    app.run(host=os.environ.get('HOST', '0.0.0.0'), 
            port=int(os.environ.get('PORT', 5000)))
