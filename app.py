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
if not app.debug:
    app.logger.setLevel(logging.INFO)
    app.logger.info('SATInsight App Starting Up')
else:
    logging.basicConfig(level=logging.DEBUG)
    app.logger.info('SATInsight App Starting in DEBUG mode')

# --- SECRET_KEY Configuration ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
if not app.config['SECRET_KEY']:
    app.logger.critical("FATAL: SECRET_KEY is NOT SET in environment variables.")
    if app.debug:
        app.logger.warning("Using a temporary SECRET_KEY for local development. DO NOT USE IN PRODUCTION.")
        app.config['SECRET_KEY'] = os.urandom(24).hex()

# --- Database Configuration ---
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    app.logger.info(f"DATABASE_URL detected. Prefix: {DATABASE_URL[:DATABASE_URL.find('://') if '://' in DATABASE_URL else 15]}...")
    if DATABASE_URL.startswith("postgres://"):
        app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        app.logger.info("Configured for PostgreSQL (Render/Heroku style via replace).")
    elif DATABASE_URL.startswith("postgresql://"):
        app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
        app.logger.info("Configured for PostgreSQL (standard URI).")
    else:
        app.logger.warning(f"DATABASE_URL provided but not 'postgres://' or 'postgresql://'. Using as is: {DATABASE_URL}")
        app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
else:
    app.logger.warning("DATABASE_URL NOT FOUND in environment. Falling back to local SQLite.")
    instance_path = os.path.join(app.instance_path)
    if not os.path.exists(instance_path):
        try:
            os.makedirs(instance_path)
            app.logger.info(f"Created instance folder for SQLite: {instance_path}")
        except OSError as e:
            app.logger.error(f"Could not create instance folder '{instance_path}': {e}", exc_info=True)
    sqlite_db_file = os.path.join(instance_path, 'sattest.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + sqlite_db_file
    app.logger.info(f"SQLite database configured at: {sqlite_db_file}")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'warning'

# --- Database Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    scores = db.relationship('Score', backref='user', lazy='dynamic')

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
    app.logger.debug(f"load_user attempt for ID: {user_id}")
    try:
        user = db.session.get(User, int(user_id))
        if not user:
            app.logger.warning(f"load_user: No user found for ID {user_id}")
        return user
    except ValueError:
        app.logger.warning(f"load_user: Invalid user_id format: {user_id}")
        return None
    except Exception as e:
        app.logger.error(f"Error in load_user for ID {user_id}: {e}", exc_info=True)
        return None

# --- Question Data ---
# Ensure this section defines all your questions.
# The TOTAL_QUESTIONS is derived from the length of these lists.
# If you see 4 questions, it's because these lists only sum to 4 questions in your current code.
QUESTIONS_DATA = {
    "math": [ # 10 Math Questions
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
    "reading_writing": [ # 20 Reading & Writing Questions (mostly placeholders)
        {"id": "rw1", "module": 1, "passage": "The following is an excerpt from a short story...", "text": "What is Sarah's profession?", "options": ["Ghost hunter", "Historian", "Journalist", "Librarian"], "correctAnswer": "Journalist", "topic": "Information and Ideas", "difficulty": "Easy"},
        {"id": "rw2", "module": 1, "text": "Placeholder R&W Question 2: Identify the main idea.", "options": ["A", "B", "C", "D"], "correctAnswer": "A", "topic": "Main Idea", "difficulty": "Medium"},
        {"id": "rw3", "module": 1, "text": "Placeholder R&W Question 3: Vocabulary in context.", "options": ["A", "B", "C", "D"], "correctAnswer": "B", "topic": "Vocabulary", "difficulty": "Easy"},
        {"id": "rw4", "module": 1, "passage": "This is a sample passage for rw4.", "text": "Placeholder R&W Question 4: Inference from passage.", "options": ["A", "B", "C", "D"], "correctAnswer": "C", "topic": "Inference", "difficulty": "Medium"},
        {"id": "rw5", "module": 1, "text": "Placeholder R&W Question 5: Grammar usage.", "options": ["A", "B", "C", "D"], "correctAnswer": "D", "topic": "Grammar", "difficulty": "Easy"},
        {"id": "rw6", "module": 1, "text": "Placeholder R&W Question 6: Author's purpose.", "options": ["A", "B", "C", "D"], "correctAnswer": "A", "topic": "Author's Purpose", "difficulty": "Hard"},
        {"id": "rw7", "module": 1, "passage": "Another sample passage for rw7.", "text": "Placeholder R&W Question 7: Detail from passage.", "options": ["A", "B", "C", "D"], "correctAnswer": "B", "topic": "Detail", "difficulty": "Easy"},
        {"id": "rw8", "module": 1, "text": "Placeholder R&W Question 8: Sentence structure.", "options": ["A", "B", "C", "D"], "correctAnswer": "C", "topic": "Sentence Structure", "difficulty": "Medium"},
        {"id": "rw9", "module": 1, "text": "Placeholder R&W Question 9: Tone of the passage.", "options": ["A", "B", "C", "D"], "correctAnswer": "D", "topic": "Tone", "difficulty": "Medium"},
        {"id": "rw10", "module": 1, "text": "Placeholder R&W Question 10: Comparative analysis.", "options": ["A", "B", "C", "D"], "correctAnswer": "A", "topic": "Analysis", "difficulty": "Hard"},
        {"id": "rw11", "module": 1, "passage": "Passage for question rw11.", "text": "Placeholder R&W Question 11: Purpose of a paragraph.", "options": ["A", "B", "C", "D"], "correctAnswer": "B", "topic": "Paragraph Purpose", "difficulty": "Medium"},
        {"id": "rw12", "module": 1, "text": "Placeholder R&W Question 12: Identify a logical flaw.", "options": ["A", "B", "C", "D"], "correctAnswer": "C", "topic": "Logical Reasoning", "difficulty": "Hard"},
        {"id": "rw13", "module": 1, "text": "Placeholder R&W Question 13: Word choice.", "options": ["A", "B", "C", "D"], "correctAnswer": "D", "topic": "Word Choice", "difficulty": "Medium"},
        {"id": "rw14", "module": 1, "text": "Placeholder R&W Question 14: Punctuation.", "options": ["A", "B", "C", "D"], "correctAnswer": "A", "topic": "Punctuation", "difficulty": "Easy"},
        {"id": "rw15", "module": 1, "passage": "Sample text for rw15.", "text": "Placeholder R&W Question 15: Evidence support.", "options": ["A", "B", "C", "D"], "correctAnswer": "B", "topic": "Evidence", "difficulty": "Medium"},
        {"id": "rw16", "module": 1, "text": "Placeholder R&W Question 16: Literary device.", "options": ["A", "B", "C", "D"], "correctAnswer": "C", "topic": "Literary Devices", "difficulty": "Hard"},
        {"id": "rw17", "module": 1, "text": "Placeholder R&W Question 17: Transition words.", "options": ["A", "B", "C", "D"], "correctAnswer": "D", "topic": "Transitions", "difficulty": "Easy"},
        {"id": "rw18", "module": 1, "text": "Placeholder R&W Question 18: Author's claim.", "options": ["A", "B", "C", "D"], "correctAnswer": "A", "topic": "Author's Claim", "difficulty": "Medium"},
        {"id": "rw19", "module": 1, "passage": "Final placeholder passage for rw19.", "text": "Placeholder R&W Question 19: Summarize.", "options": ["A", "B", "C", "D"], "correctAnswer": "B", "topic": "Summarization", "difficulty": "Medium"},
        {"id": "rw20", "module": 1, "text": "The word 'ubiquitous' means:", "options": ["Rare and hard to find", "Present, appearing, or found everywhere", "Expensive and luxurious", "Temporary and fleeting"], "correctAnswer": "Present, appearing, or found everywhere", "topic": "Craft and Structure (Vocabulary)", "difficulty": "Hard"}
    ]
}
ALL_QUESTIONS = QUESTIONS_DATA["math"] + QUESTIONS_DATA["reading_writing"]
ALL_QUESTIONS_MAP = {q['id']: q for q in ALL_QUESTIONS}
ORDERED_QUESTION_IDS = [q['id'] for q in ALL_QUESTIONS]
TOTAL_QUESTIONS = len(ALL_QUESTIONS) # This should be 30 if above data is complete
TEST_DURATION_MINUTES = 30

app.logger.info(f"Total questions loaded: {TOTAL_QUESTIONS}") # Log how many questions were loaded

def initialize_test_session():
    app.logger.info(f"Initializing test session for user: {current_user.id if current_user.is_authenticated else 'Anonymous'}")
    # Clear previous test session more thoroughly if needed, or rely on specific key popping at end of test
    session.pop('current_question_index', None)
    session.pop('answers', None)
    session.pop('start_time', None)
    session.pop('test_questions_ids_ordered', None)
    session.pop('marked_for_review', None)

    session['current_question_index'] = 0
    session['answers'] = {}
    session['start_time'] = datetime.datetime.now().isoformat()
    session['test_questions_ids_ordered'] = ORDERED_QUESTION_IDS[:]
    session['marked_for_review'] = {}
    session.modified = True

def calculate_mock_score(answers):
    correct_count = 0
    math_correct = 0
    rw_correct = 0

    math_total_qs_in_test = sum(1 for q_id in ORDERED_QUESTION_IDS if q_id.startswith('m'))
    rw_total_qs_in_test = sum(1 for q_id in ORDERED_QUESTION_IDS if q_id.startswith('rw'))
    
    app.logger.debug(f"Calculating score. Math Qs in test: {math_total_qs_in_test}, R&W Qs in test: {rw_total_qs_in_test}. Total ORDERED_QUESTION_IDS: {len(ORDERED_QUESTION_IDS)}")
    app.logger.debug(f"User answers for score calculation: {answers}")

    for q_id, user_answer in answers.items():
        question_detail = ALL_QUESTIONS_MAP.get(q_id)
        if not question_detail:
            app.logger.warning(f"calculate_mock_score: Question ID '{q_id}' from user answers not found in ALL_QUESTIONS_MAP.")
            continue
        
        is_math = q_id.startswith('m')
        
        if user_answer == question_detail['correctAnswer']:
            correct_count += 1
            if is_math:
                math_correct += 1
            else:
                rw_correct += 1
            
    mock_math_score = 200 + int((math_correct / max(1, math_total_qs_in_test)) * 600) if math_total_qs_in_test > 0 else 200
    mock_rw_score = 200 + int((rw_correct / max(1, rw_total_qs_in_test)) * 600) if rw_total_qs_in_test > 0 else 200
    
    mock_total_score = mock_math_score + mock_rw_score
    
    mock_math_score = max(200, min(800, mock_math_score))
    mock_rw_score = max(200, min(800, mock_rw_score))
    mock_total_score = max(400, min(1600, mock_total_score))
    
    weaknesses = []
    recommendations = []
    if TOTAL_QUESTIONS > 0: # Only add weaknesses if there were questions
        if math_total_qs_in_test > 0 and (math_correct / math_total_qs_in_test) < 0.6:
            weaknesses.append("Math Concepts")
            recommendations.append("Review foundational math topics and practice regularly.")
        if rw_total_qs_in_test > 0 and (rw_correct / rw_total_qs_in_test) < 0.6:
            weaknesses.append("Reading & Writing Skills")
            recommendations.append("Focus on grammar rules, vocabulary, and passage analysis techniques.")
        if not weaknesses :
            weaknesses.append("Good overall performance!")
            recommendations.append("Continue practicing with varied question types and explore advanced topics.")
    else:
        weaknesses.append("No questions were processed for scoring.")
        recommendations.append("Please check the test configuration or question data.")

    return {
        "total_score": mock_total_score, "math_score": mock_math_score, "rw_score": mock_rw_score,
        "correct_count": correct_count, "total_answered": len(answers),
        "total_test_questions": TOTAL_QUESTIONS,
        "weaknesses": weaknesses, "recommendations": recommendations
    }

def generate_csv_report(score_obj):
    output = io.StringIO()
    writer = csv.writer(output)
    headers = [
        "Question Number", "Section", "Skill Type", "Your Answer", "Correct Answer", "Outcome",
        "QuestionID", "Module", "Difficulty", "QuestionText", "AllOptions", "ScoreID", "TestDate"
    ]
    writer.writerow(headers)

    if not score_obj or not score_obj.answers_data:
        app.logger.warning(f"generate_csv_report: No score object or answers_data for score_id {score_obj.id if score_obj else 'N/A'}.")
        writer.writerow(["N/A"] * len(headers[:-2]) + [score_obj.id if score_obj else "N/A", "N/A"]) # Fill with N/A
        output.seek(0)
        return output.getvalue()
    
    try:
        user_answers_dict = json.loads(score_obj.answers_data)
    except json.JSONDecodeError:
        app.logger.error(f"generate_csv_report: JSONDecodeError for answers_data, score_id {score_obj.id}.", exc_info=True)
        writer.writerow(["Error decoding answers"] + ["N/A"] * (len(headers) - 3) + [score_obj.id, score_obj.timestamp.strftime('%Y-%m-%d %H:%M:%S') if score_obj.timestamp else "N/A"])
        output.seek(0)
        return output.getvalue()

    test_date_str = score_obj.timestamp.strftime('%Y-%m-%d %H:%M:%S') if score_obj.timestamp else "N/A"
    
    for idx, q_id in enumerate(ORDERED_QUESTION_IDS):
        question_detail = ALL_QUESTIONS_MAP.get(q_id)
        question_sequence_number = idx + 1
        if not question_detail:
            writer.writerow([
                question_sequence_number, "Unknown Section", "N/A", "N/A", "N/A", "Question Detail Missing",
                q_id, "N/A", "N/A", f"Details not found for Q_ID: {q_id}", "[]",
                score_obj.id, test_date_str
            ])
            continue

        section_val = "Math" if q_id.startswith('m') else "Reading & Writing"
        skill_type_val = question_detail.get("topic", "N/A")
        user_answer_val = user_answers_dict.get(q_id, "Not Answered")
        correct_answer_val = question_detail.get("correctAnswer", "N/A")
        
        outcome_val = "Not Answered"
        if user_answer_val != "Not Answered":
            outcome_val = "Correct" if user_answer_val == correct_answer_val else "Incorrect"
        
        module_val = question_detail.get("module", "N/A")
        difficulty_val = question_detail.get("difficulty", "N/A")
        question_text_val = question_detail.get("text", "N/A")
        if question_detail.get("passage"):
             question_text_val = f"[Passage Based] {question_text_val}"
        all_options_json = json.dumps(question_detail.get("options", []))
        
        writer.writerow([
            question_sequence_number, section_val, skill_type_val, user_answer_val, correct_answer_val, outcome_val,
            q_id, module_val, difficulty_val, question_text_val, all_options_json,
            score_obj.id, test_date_str
        ])
    output.seek(0)
    return output.getvalue()

# --- Error Handling ---
@app.errorhandler(Exception)
def handle_general_exception(e):
    # Log the exception with stack trace
    app.logger.error(f"Unhandled application exception: {e}", exc_info=True)
    # For non-HTTP exceptions, you might want a generic error message.
    # For HTTP exceptions (like 404, 500 from abort()), Werkzeug handles them by default
    # but you can customize their pages here too.
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        # You can render a custom template for specific HTTP errors
        # return render_template(f"errors/{e.code}.html", error=e), e.code
        return render_template("error_page.html", error_code=e.code, error_message=e.description, error_name=e.name), e.code
    
    # For other Python exceptions that were not caught
    return render_template("error_page.html", error_message="An unexpected internal error occurred. Our team has been notified."), 500

# --- Routes ---
@app.route('/')
def index():
    app.logger.info(f"Route / accessed by user: {current_user.id if current_user.is_authenticated else 'Anonymous'}")
    return render_template('index.html', total_questions=TOTAL_QUESTIONS, duration=TEST_DURATION_MINUTES, now=datetime.datetime.utcnow())

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username','').strip() # Add strip
        password = request.form.get('password')
        app.logger.info(f"Registration attempt for username: '{username}'")

        if not username or not password:
            flash('Username and password are required.', 'warning')
            return redirect(url_for('register'))
        
        if len(username) < 3: # Example validation
            flash('Username must be at least 3 characters long.', 'warning')
            return redirect(url_for('register'))
        if len(password) < 6: # Example validation
            flash('Password must be at least 6 characters long.', 'warning')
            return redirect(url_for('register'))

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose a different one.', 'danger')
            return redirect(url_for('register'))
        
        new_user = User(username=username)
        new_user.set_password(password)
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful! Please log in.', 'success')
            app.logger.info(f"User '{username}' registered successfully.")
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Database error during registration for '{username}': {e}", exc_info=True)
            flash('An error occurred during registration. Please try again.', 'danger')
            return redirect(url_for('register'))
    return render_template('register.html', now=datetime.datetime.utcnow())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password')
        app.logger.info(f"Login attempt for username: '{username}'")
        user = User.query.filter_by(username=username).first() # Case-sensitive username
        if user and user.check_password(password):
            login_user(user, remember=(request.form.get('remember') == 'on')) # Checkbox value is 'on' if checked
            flash('Logged in successfully!', 'success')
            app.logger.info(f"User '{username}' logged in successfully.")
            next_page = request.args.get('next')
            # Basic Open Redirect protection
            if next_page and not (next_page.startswith('/') or next_page.startswith(request.host_url)):
                app.logger.warning(f"Invalid 'next' URL '{next_page}' provided during login for user '{username}'. Redirecting to index.")
                next_page = url_for('index') # Default to index if next_page is suspicious
            return redirect(next_page or url_for('index'))
        else:
            flash('Invalid username or password.', 'danger')
            app.logger.warning(f"Failed login attempt for username: '{username}'")
    return render_template('login.html', now=datetime.datetime.utcnow())

@app.route('/logout')
@login_required
def logout():
    app.logger.info(f"User '{current_user.username}' logging out.")
    logout_user()
    session.clear() # Clear the whole session on logout for good measure
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard/')
@login_required
def dashboard():
    app.logger.info(f"Dashboard accessed by user: '{current_user.username}'")
    try:
        user_scores = current_user.scores.order_by(Score.timestamp.desc()).all()
    except Exception as e:
        app.logger.error(f"Error fetching scores for dashboard for user '{current_user.username}': {e}", exc_info=True)
        flash("Could not load scores at this time. Please try again later.", "danger")
        user_scores = []
    return render_template('dashboard.html', scores=user_scores, now=datetime.datetime.utcnow())

@app.route('/start_test', methods=['POST'])
@login_required
def start_test():
    app.logger.info(f"User '{current_user.username}' is starting a new test.")
    initialize_test_session()
    return redirect(url_for('test_question_page', q_idx=0))

@app.route('/test/question/<int:q_idx>', methods=['GET', 'POST'])
@login_required
def test_question_page(q_idx):
    app.logger.debug(f"Question page {q_idx} for user '{current_user.username}', method: {request.method}")
    
    required_session_keys = ['test_questions_ids_ordered', 'answers', 'start_time', 'marked_for_review']
    if not all(key in session for key in required_session_keys) or not session.get('test_questions_ids_ordered'):
        flash('Your test session is invalid or has expired. Please start a new test.', 'warning')
        app.logger.warning(f"Invalid test session access by user '{current_user.username}' for q_idx {q_idx}. Missing keys or no ordered_ids.")
        return redirect(url_for('index'))

    ordered_ids = session['test_questions_ids_ordered']
    if not (0 <= q_idx < len(ordered_ids)):
        valid_q_idx = session.get('current_question_index', 0)
        if not (0 <= valid_q_idx < len(ordered_ids)): valid_q_idx = 0
        flash('The requested question number is invalid. Redirecting to your current question.', 'danger')
        app.logger.warning(f"Out-of-bounds q_idx {q_idx} (max: {len(ordered_ids)-1}) for user '{current_user.username}'. Redirecting to {valid_q_idx}.")
        return redirect(url_for('test_question_page', q_idx=valid_q_idx))

    session['current_question_index'] = q_idx # Update current index
    question_id = ordered_ids[q_idx]
    question = ALL_QUESTIONS_MAP.get(question_id)

    if not question:
        flash('Error: Question data could not be loaded. Please restart the test.', 'danger')
        app.logger.error(f"Question ID '{question_id}' (index {q_idx}) not found in ALL_QUESTIONS_MAP for user '{current_user.username}'. Test integrity compromised.")
        initialize_test_session() # Reset session to prevent further errors with bad state
        return redirect(url_for('index'))

    if request.method == 'POST':
        app.logger.debug(f"POST for q_idx {q_idx} by '{current_user.username}'. Form: {request.form}")
        
        selected_option = request.form.get('answer')
        if selected_option:
            session['answers'][question_id] = selected_option
        # If no answer is selected, no change to session['answers'][question_id] for this POST
        # To allow "unselecting" an answer, you'd need different client-side logic (e.g., a clear button)

        if 'mark_review' in request.form and request.form.get('mark_review') == 'true':
            session['marked_for_review'][question_id] = True
        else: # Checkbox not submitted or value not 'true', so unmark
            session['marked_for_review'].pop(question_id, None)
        
        session.modified = True

        action = request.form.get('action') # From hidden 'Next'/'Back'
        if action == 'next':
            if q_idx + 1 < len(ordered_ids):
                return redirect(url_for('test_question_page', q_idx=q_idx + 1))
            else:
                return redirect(url_for('results'))
        elif action == 'back':
            if q_idx > 0:
                return redirect(url_for('test_question_page', q_idx=q_idx - 1))
        # Default redirect (e.g., after 'Mark for Review' checkbox submit)
        return redirect(url_for('test_question_page', q_idx=q_idx))

    # GET request:
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
    app.logger.info(f"User '{current_user.username}' viewing results.")
    if 'answers' not in session or 'start_time' not in session: # Check essential keys
        flash('Test data is incomplete or your session has expired. Please start a new test.', 'warning')
        app.logger.warning(f"Results page: Missing 'answers' or 'start_time' in session for user '{current_user.username}'.")
        return redirect(url_for('index'))

    user_submitted_answers = session.get('answers', {}) # Default to empty dict
    start_time_iso = session.get('start_time')

    if not start_time_iso: # Should not happen if previous check passed, but defensive
        flash('Critical error: Test start time missing. Cannot calculate results. Please restart.', 'danger')
        app.logger.error(f"Results page: 'start_time' is None/empty in session for user '{current_user.username}'.")
        return redirect(url_for('index'))

    try:
        start_time = datetime.datetime.fromisoformat(start_time_iso)
    except (ValueError, TypeError) as e:
        app.logger.error(f"Invalid 'start_time' format ('{start_time_iso}') for user '{current_user.username}': {e}", exc_info=True)
        flash('There was an error processing your test start time. Results might be affected. Please start a new test.', 'danger')
        return redirect(url_for('index'))

    end_time = datetime.datetime.now(datetime.timezone.utc) # Use timezone-aware now
    time_taken_seconds = (end_time - start_time.replace(tzinfo=datetime.timezone.utc if start_time.tzinfo is None else None)).total_seconds() # Ensure consistent timezone comparison
    
    results_summary = calculate_mock_score(user_submitted_answers)
    results_summary['time_taken_formatted'] = f"{int(time_taken_seconds // 60)}m {int(time_taken_seconds % 60)}s"
    
    answers_json_string = json.dumps(user_submitted_answers)
    score_id_for_template = None
    try:
        new_score = Score(user_id=current_user.id,
                          total_score=results_summary['total_score'], math_score=results_summary['math_score'],
                          rw_score=results_summary['rw_score'], correct_count=results_summary['correct_count'],
                          total_answered=results_summary['total_answered'], answers_data=answers_json_string,
                          timestamp=end_time) # Use server's end_time
        db.session.add(new_score)
        db.session.commit()
        score_id_for_template = new_score.id
        app.logger.info(f"Score (ID: {new_score.id}) saved for user '{current_user.username}'.")
        flash('Your test results have been successfully saved!', 'success')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Database error while saving score for user '{current_user.username}': {e}", exc_info=True)
        flash('A database error occurred while saving your score. Please try submitting again or contact support if the issue persists.', 'danger')

    # Clean up test-specific session data after saving results
    session_keys_to_pop = ['current_question_index', 'answers', 'start_time', 
                           'test_questions_ids_ordered', 'marked_for_review']
    for key in session_keys_to_pop:
        session.pop(key, None)
    session.modified = True # Ensure session changes are saved
        
    return render_template('results_page.html', results=results_summary, score_id=score_id_for_template, now=datetime.datetime.utcnow())

@app.route('/download_report/<int:score_id>/<string:report_format>')
@login_required
def download_report(score_id, report_format):
    app.logger.info(f"User '{current_user.username}' attempting to download report for score_id {score_id}, format {report_format}.")
    score_to_download = db.session.get(Score, score_id)
    
    if not score_to_download:
        flash(f"Score report with ID {score_id} not found.", "danger")
        return redirect(request.referrer or url_for('dashboard'))
    if score_to_download.user_id != current_user.id:
        flash("You do not have permission to access this score report.", "danger")
        app.logger.warning(f"Access denied for user '{current_user.username}' to score_id {score_id} (belongs to user {score_to_download.user_id}).")
        return redirect(url_for('dashboard'))

    if report_format.lower() == 'csv':
        try:
            csv_data = generate_csv_report(score_to_download)
            return Response(
                csv_data,
                mimetype="text/csv",
                headers={"Content-disposition": f"attachment; filename=sat_detailed_report_{score_id}.csv"}
            )
        except Exception as e:
            app.logger.error(f"Error generating CSV report for score_id {score_id}: {e}", exc_info=True)
            flash("Could not generate CSV report at this time.", "danger")
            return redirect(request.referrer or url_for('dashboard'))
    else:
        flash(f"Unsupported report format: {report_format}.", "warning")
        return redirect(request.referrer or url_for('dashboard'))

@app.route('/reset_test', methods=['POST'])
@login_required
def reset_test():
    app.logger.info(f"User '{current_user.username}' manually resetting test session.")
    session_keys_to_pop = ['current_question_index', 'answers', 'start_time', 
                           'test_questions_ids_ordered', 'marked_for_review']
    for key in session_keys_to_pop:
        session.pop(key, None)
    session.modified = True
    flash('Your test session has been reset. You can start a new test.', 'info')
    return redirect(url_for('index'))

@app.cli.command("init-db")
def init_db_command():
    """Creates database tables from models if they don't already exist."""
    try:
        with app.app_context():
            # This will create tables for all models defined that don't yet exist.
            # It won't update existing tables if models change (use migrations for that).
            db.create_all()
        app.logger.info("Command 'flask init-db' executed: Database tables checked/created.")
        print("Initialized the database: Tables checked/created.")
    except Exception as e:
        print(f"Error during 'flask init-db' command: {e}")
        app.logger.error(f"Error during 'flask init-db' command: {e}", exc_info=True)

# This block is for running with `python app.py` (Flask's dev server)
# For Render, Gunicorn (or another WSGI server) is the entry point via Procfile
if __name__ == '__main__':
    # Set FLASK_DEBUG=1 in your environment for local debug mode
    is_debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.logger.info(f"Starting Flask development server (Debug mode: {is_debug_mode})...")
    # For local development, ensure tables exist. Run 'flask init-db' first.
    # with app.app_context():
    # db.create_all() # This can be here for convenience in local dev if you don't use flask init-db
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=is_debug_mode)
