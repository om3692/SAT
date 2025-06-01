from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
import datetime
import random
import io
import csv
import json # Required for storing and parsing answers_data

# --- Application Setup ---
app = Flask(__name__)

# SECRET_KEY Configuration
# For Heroku, set a fixed SECRET_KEY in environment variables.
# For local development, os.urandom(24) is fine but will invalidate sessions on restart.
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24))

# Database Configuration
# Use DATABASE_URL from environment variables if available (for Heroku/PostgreSQL)
# Otherwise, fall back to local SQLite database
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    # Heroku's DATABASE_URL needs to be slightly modified for SQLAlchemy
    # SQLAlchemy expects postgresql://, not postgres://
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL.replace("postgres://", "postgresql://", 1)
elif DATABASE_URL:
    # For other PostgreSQL connections that might already use postgresql://
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
else:
    # Local SQLite setup
    # Ensure the instance folder exists for SQLite database
    instance_path = os.path.join(app.instance_path)
    if not os.path.exists(instance_path):
        os.makedirs(instance_path)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(instance_path, 'sattest.db')


app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- Database Models ---
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
    total_answered = db.Column(db.Integer)
    answers_data = db.Column(db.Text, nullable=True)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Question Data ---
QUESTIONS_DATA = {
    "math": [
        {"id": "m1", "module": 1, "text": "If 5x + 6 = 10, what is the value of 5x + 3?", "options": ["1", "3", "4", "7"], "correctAnswer": "7", "topic": "Algebra", "difficulty": "Easy"},
        {"id": "m2", "module": 1, "text": "A rectangular garden is 10 feet long and 5 feet wide. What is its area in square feet?", "options": ["15", "25", "50", "100"], "correctAnswer": "50", "topic": "Geometry", "difficulty": "Easy"},
        {"id": "m3", "module": 1, "text": "What is 20% of 200?", "options": ["20", "40", "50", "100"], "correctAnswer": "40", "topic": "Problem-Solving and Data Analysis", "difficulty": "Easy"},
        {"id": "m4", "module": 1, "text": "If a circle has a radius of 3, what is its circumference? (Use π ≈ 3.14)", "options": ["9.42", "18.84", "28.26", "6.00"], "correctAnswer": "18.84", "topic": "Geometry", "difficulty": "Medium"},
        {"id": "m5", "module": 1, "text": "Solve for y: 3(y - 2) = 9", "options": ["3", "4", "5", "6"], "correctAnswer": "5", "topic": "Algebra", "difficulty": "Medium"},
        {"id": "m6", "module": 1, "text": "A car travels 120 miles in 2 hours. What is its average speed in miles per hour?", "options": ["50 mph", "60 mph", "70 mph", "80 mph"], "correctAnswer": "60 mph", "topic": "Problem-Solving and Data Analysis", "difficulty": "Easy"},
        {"id": "m7", "module": 1, "text": "What is the next number in the sequence: 2, 5, 8, 11, ...?", "options": ["12", "13", "14", "15"], "correctAnswer": "14", "topic": "Algebra", "difficulty": "Easy"},
        {"id": "m8", "module": 1, "text": "If a triangle has angles 45°, 45°, and x°, what is the value of x?", "options": ["45°", "60°", "90°", "100°"], "correctAnswer": "90°", "topic": "Geometry", "difficulty": "Medium"},
        {"id": "m9", "module": 1, "text": "Simplify the expression: (2^3) * (2^2)", "options": ["2^1", "2^5", "2^6", "4^5"], "correctAnswer": "2^5", "topic": "Algebra (Exponents)", "difficulty": "Medium"},
        {"id": "m10", "module": 1, "text": "A survey of 50 students found that 30 like apples and 25 like bananas. If 10 students like both, how many students like neither?", "options": ["0", "5", "10", "15"], "correctAnswer": "5", "topic": "Problem-Solving and Data Analysis (Sets)", "difficulty": "Hard"}
    ],
    "reading_writing": [
        {"id": "rw1", "module": 1, "passage": "The following is an excerpt from a short story. \n'The old house stood on a hill overlooking the town. It had been empty for years, and locals said it was haunted. But Sarah, a young journalist, was determined to uncover its secrets.'", "text": "What is Sarah's profession?", "options": ["Ghost hunter", "Historian", "Journalist", "Librarian"], "correctAnswer": "Journalist", "topic": "Information and Ideas", "difficulty": "Easy"},
        # ... (rest of your reading_writing questions remain the same) ...
        {"id": "rw20", "module": 1, "text": "The word 'ubiquitous' means:", "options": ["Rare and hard to find", "Present, appearing, or found everywhere", "Expensive and luxurious", "Temporary and fleeting"], "correctAnswer": "Present, appearing, or found everywhere", "topic": "Craft and Structure (Vocabulary)", "difficulty": "Hard"}
    ]
}
ALL_QUESTIONS = QUESTIONS_DATA["math"] + QUESTIONS_DATA["reading_writing"]
ALL_QUESTIONS_MAP = {q['id']: q for q in ALL_QUESTIONS}
ORDERED_QUESTION_IDS = [q['id'] for q in ALL_QUESTIONS]

TOTAL_QUESTIONS = len(ALL_QUESTIONS)
TEST_DURATION_MINUTES = 30

def initialize_test_session():
    session['current_question_index'] = 0
    session['answers'] = {}
    session['start_time'] = datetime.datetime.now().isoformat()
    session['test_questions_ids_ordered'] = ORDERED_QUESTION_IDS[:]
    session['marked_for_review'] = {}

def calculate_mock_score(answers):
    correct_count = 0
    math_correct = 0
    math_total = 0
    rw_correct = 0
    rw_total = 0
    for q_id, user_answer in answers.items():
        question_detail = ALL_QUESTIONS_MAP.get(q_id)
        if not question_detail: continue
        is_math = any(q_id == m_q['id'] for m_q in QUESTIONS_DATA['math'])
        if is_math: math_total += 1
        else: rw_total += 1
        if user_answer == question_detail['correctAnswer']:
            correct_count += 1
            if is_math: math_correct += 1
            else: rw_correct += 1
    mock_math_score = 200 + int((math_correct / max(1, math_total)) * 600)
    mock_rw_score = 200 + int((rw_correct / max(1, rw_total)) * 600)
    mock_total_score = mock_math_score + mock_rw_score
    mock_math_score = max(200, min(800, mock_math_score))
    mock_rw_score = max(200, min(800, mock_rw_score))
    mock_total_score = max(400, min(1600, mock_total_score))
    weaknesses = []
    recommendations = []
    if (math_correct / max(1, math_total)) < 0.6: weaknesses.append("Algebra Concepts (Math)"); recommendations.append("Review foundational algebra topics.")
    if (rw_correct / max(1, rw_total)) < 0.6: weaknesses.append("Grammar Rules (Reading & Writing)"); recommendations.append("Focus on Standard English Conventions.")
    if not weaknesses: weaknesses.append("Good overall performance!"); recommendations.append("Explore advanced topics.")
    return {"total_score": mock_total_score, "math_score": mock_math_score, "rw_score": mock_rw_score, "correct_count": correct_count, "total_answered": len(answers), "weaknesses": weaknesses, "recommendations": recommendations}

def generate_csv_report(score_obj):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Question Number", "Section", "Skill Type", "Your Answer", "Correct Answer", "Outcome",
        "QuestionID", "Module", "Difficulty", "QuestionText", "AllOptions", "ScoreID", "TestDate"
    ])
    if not score_obj.answers_data:
        writer.writerow([
            "N/A", "N/A", "N/A", "N/A", "N/A", "No detailed answer data",
            "N/A", "N/A", "N/A", "N/A", "N/A", score_obj.id if score_obj else "N/A",
            score_obj.timestamp.strftime('%Y-%m-%d %H:%M:%S') if score_obj else "N/A"
        ])
        output.seek(0)
        return output.getvalue()
    try:
        user_answers_dict = json.loads(score_obj.answers_data)
    except json.JSONDecodeError:
        writer.writerow([
            "N/A", "N/A", "N/A", "N/A", "N/A", "Error decoding answers",
            "N/A", "N/A", "N/A", "N/A", "N/A", score_obj.id,
            score_obj.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        ])
        output.seek(0)
        return output.getvalue()

    test_date_str = score_obj.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    score_id_val = score_obj.id
    question_sequence_number = 0

    for q_id in ORDERED_QUESTION_IDS:
        question_sequence_number += 1
        question_detail = ALL_QUESTIONS_MAP.get(q_id)
        if not question_detail:
            writer.writerow([
                question_sequence_number, "Unknown", "Unknown", "N/A", "N/A", "Question detail missing",
                q_id, "Unknown", "Unknown", f"Details not found for Q_ID: {q_id}",
                "[]", score_id_val, test_date_str
            ])
            continue
        section_val = "Math" if any(q_id == m_q['id'] for m_q in QUESTIONS_DATA['math']) else "Reading & Writing"
        skill_type_val = question_detail.get("topic", "N/A")
        user_answer_val = user_answers_dict.get(q_id, "Not Answered")
        correct_answer_val = question_detail.get("correctAnswer", "N/A")
        outcome_val = "Correct" if user_answer_val == correct_answer_val else "Incorrect"
        if user_answer_val == "Not Answered": outcome_val = "Not Answered"
        module_val = question_detail.get("module", "N/A")
        difficulty_val = question_detail.get("difficulty", "N/A")
        question_text_val = question_detail.get("text", "N/A")
        passage_text = question_detail.get("passage")
        if passage_text:
             question_text_val = f"[PASSAGE-BASED Q:{question_sequence_number}] {question_text_val}"
        all_options_json = json.dumps(question_detail.get("options", []))
        writer.writerow([
            question_sequence_number, section_val, skill_type_val, user_answer_val, correct_answer_val, outcome_val,
            q_id, module_val, difficulty_val, question_text_val, all_options_json, score_id_val, test_date_str
        ])
    output.seek(0)
    return output.getvalue()

# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html', total_questions=TOTAL_QUESTIONS, duration=TEST_DURATION_MINUTES, now=datetime.datetime.utcnow())

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose a different one.', 'danger')
            return redirect(url_for('register'))
        if not username or not password:
            flash('Username and password are required.', 'warning')
            return redirect(url_for('register'))
        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', now=datetime.datetime.utcnow())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=request.form.get('remember'))
            flash('Logged in successfully!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html', now=datetime.datetime.utcnow())

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard/')
@login_required
def dashboard():
    user_scores = Score.query.filter_by(user_id=current_user.id).order_by(Score.timestamp.desc()).all()
    return render_template('dashboard.html', scores=user_scores, now=datetime.datetime.utcnow())

@app.route('/start_test', methods=['POST'])
@login_required
def start_test():
    initialize_test_session()
    return redirect(url_for('test_question_page', q_idx=0))

@app.route('/test/question/<int:q_idx>', methods=['GET', 'POST'])
@login_required
def test_question_page(q_idx):
    if 'test_questions_ids_ordered' not in session or not session['test_questions_ids_ordered']:
        flash('Test session not found or expired. Please start a new test.', 'warning')
        return redirect(url_for('index'))
    ordered_ids = session['test_questions_ids_ordered']
    if not 0 <= q_idx < len(ordered_ids):
        current_q_idx_in_session = session.get('current_question_index', 0)
        flash('Invalid question number.', 'danger')
        return redirect(url_for('test_question_page', q_idx=current_q_idx_in_session))
    session['current_question_index'] = q_idx
    question_id = ordered_ids[q_idx]
    question = ALL_QUESTIONS_MAP.get(question_id)
    if not question:
        flash('Error: Question not found.', 'danger')
        return redirect(url_for('index'))
    if request.method == 'POST':
        selected_option = request.form.get('answer')
        if selected_option: session['answers'][question_id] = selected_option
        if 'mark_review' in request.form: session['marked_for_review'][question_id] = True
        elif question_id in session['marked_for_review']: session['marked_for_review'].pop(question_id, None)
        session.modified = True # Ensure session changes are saved
        action = request.form.get('action')
        if action == 'next':
            if q_idx + 1 < len(ordered_ids): return redirect(url_for('test_question_page', q_idx=q_idx + 1))
            else: return redirect(url_for('results'))
        elif action == 'back':
            if q_idx > 0: return redirect(url_for('test_question_page', q_idx=q_idx - 1))
        return redirect(url_for('test_question_page', q_idx=q_idx))

    current_section_name = "Math" if any(question_id == m_q['id'] for m_q in QUESTIONS_DATA['math']) else "Reading & Writing"
    current_module = question.get('module', 1)
    is_marked = session.get('marked_for_review', {}).get(question_id, False)
    selected_answer = session.get('answers', {}).get(question_id)
    return render_template('test_page.html', question=question, question_number=q_idx + 1, total_questions=TOTAL_QUESTIONS,
                           current_section=f"Section {1 if current_section_name == 'Math' else 2}, Module {current_module}: {current_section_name}",
                           start_time_iso=session['start_time'], test_duration_minutes=TEST_DURATION_MINUTES,
                           now=datetime.datetime.utcnow(), is_marked_for_review=is_marked,
                           selected_answer=selected_answer, q_idx=q_idx)

@app.route('/results')
@login_required
def results():
    if 'answers' not in session or 'start_time' not in session:
        flash('No answers recorded or session expired. Please start a new test.', 'warning')
        return redirect(url_for('index'))
    user_submitted_answers = session.get('answers', {})
    start_time = datetime.datetime.fromisoformat(session['start_time'])
    end_time = datetime.datetime.now()
    time_taken_seconds = (end_time - start_time).total_seconds()
    results_summary = calculate_mock_score(user_submitted_answers)
    results_summary['time_taken_formatted'] = f"{int(time_taken_seconds // 60)}m {int(time_taken_seconds % 60)}s"
    answers_json_string = json.dumps(user_submitted_answers)
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
    session_keys_to_pop = ['current_question_index', 'answers', 'start_time', 'test_questions_ids_ordered', 'marked_for_review']
    for key in session_keys_to_pop: session.pop(key, None)
    flash('Your test results have been saved!', 'success')
    return render_template('results_page.html', results=results_summary, score_id=new_score.id, now=datetime.datetime.utcnow())

@app.route('/download_report/<int:score_id>/<string:report_format>')
@login_required
def download_report(score_id, report_format):
    score_to_download = Score.query.filter_by(id=score_id, user_id=current_user.id).first_or_404()
    if report_format == 'csv':
        csv_data = generate_csv_report(score_to_download)
        return Response(csv_data, mimetype="text/csv", headers={"Content-disposition": f"attachment; filename=sat_detailed_report_{score_id}.csv"})
    else:
        flash("Invalid or unsupported report format requested.", "danger")
        return redirect(request.referrer or url_for('dashboard'))

@app.route('/reset_test', methods=['POST'])
@login_required
def reset_test():
    session_keys_to_pop = ['current_question_index', 'answers', 'start_time', 'test_questions_ids_ordered', 'marked_for_review']
    for key in session_keys_to_pop: session.pop(key, None)
    flash('Test session reset. You can start a new test.', 'info')
    return redirect(url_for('index'))

# Flask CLI command to initialize the database
@app.cli.command("init-db")
def init_db_command():
    """Creates the database tables."""
    with app.app_context():
        db.create_all()
    print("Initialized the database.")

if __name__ == '__main__':
    # For local development, debug can be controlled by FLASK_DEBUG environment variable
    # Example: FLASK_DEBUG=1 python app.py
    # Gunicorn will manage the app in production and ignore app.run()
    # The db.create_all() was here and is now moved to the 'flask init-db' command.
    app.run(debug=os.environ.get('FLASK_DEBUG', 'False').lower() == 'true',
            host='0.0.0.0',
            port=int(os.environ.get('PORT', 5000)))