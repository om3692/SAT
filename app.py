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
# Configure Flask's built-in logger
app.logger.setLevel(log_level)
# BasicConfig can be helpful for local dev; Gunicorn might handle root logger on Render.
logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s %(name)s: %(message)s')

if not is_debug_env:
    app.logger.info('SATInsight App Starting Up in Production-like mode (e.g., on Render)')
else:
    app.logger.info('SATInsight App Starting Up in DEBUG mode (local development)')

# --- SECRET_KEY Configuration ---
# CRITICAL FIX FOR RENDER: Prioritize environment variable for SECRET_KEY.
# DO NOT use os.urandom(24) directly for app.config['SECRET_KEY'] in production.
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
if not app.config['SECRET_KEY']:
    app.logger.critical("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    app.logger.critical("!!! FATAL ERROR: SECRET_KEY ENVIRONMENT VARIABLE IS NOT SET                 !!!")
    app.logger.critical("!!! Flask sessions WILL FAIL, leading to app crashes and reload loops.    !!!")
    app.logger.critical("!!! SET THIS IN YOUR RENDER SERVICE ENVIRONMENT SETTINGS IMMEDIATELY.     !!!")
    app.logger.critical("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    if is_debug_env: # Fallback for local development ONLY if FLASK_DEBUG is true
        app.logger.warning("DEVELOPMENT ONLY: Using a temporary, insecure SECRET_KEY ('dev_secret_key').")
        app.logger.warning("For consistent local dev, consider using a fixed string or python-dotenv.")
        app.config['SECRET_KEY'] = "dev_secret_key_please_change_for_local_prod_like_testing" # More stable for local dev than urandom
    # Note: If SECRET_KEY remains unset on Render, the app will still crash on session operations.

# --- Database Configuration ---
# CRITICAL FIX FOR RENDER: Prioritize environment variable for DATABASE_URL.
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    app.logger.info(f"DATABASE_URL detected from environment. Type: {DATABASE_URL.split('://')[0] if '://' in DATABASE_URL else 'Unknown'}")
    if DATABASE_URL.startswith("postgres://"): # Common for Render PostgreSQL
        app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        app.logger.info("Adjusted DATABASE_URL for SQLAlchemy (postgres:// -> postgresql://).")
    else: # Assumes postgresql:// or other SQLAlchemy compatible URI if not the Render default
        app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
        app.logger.info(f"Using provided DATABASE_URL as is: {app.config['SQLALCHEMY_DATABASE_URI']}")
else:
    app.logger.warning("DATABASE_URL environment variable NOT FOUND. Defaulting to local SQLite ('sqlite:///sattest.db').")
    app.logger.warning("IMPORTANT: For Render deployment, SQLite is NOT recommended for persistent data as its filesystem is ephemeral. "
                     "Data (users, scores) WILL BE LOST on deploys/restarts. Use Render's managed PostgreSQL service and set DATABASE_URL.")
    # Your original fallback for local SQLite:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///sattest.db'
    # For more robust local SQLite (creates 'instance' folder in your app root):
    # instance_path = os.path.join(app.instance_path)
    # if not os.path.exists(instance_path): os.makedirs(instance_path, exist_ok=True)
    # sqlite_db_file = os.path.join(instance_path, 'sattest.db')
    # app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + sqlite_db_file
    app.logger.info(f"SQLite database configured at: {app.config['SQLALCHEMY_DATABASE_URI']}")

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
def load_user(user_id_str): # user_id from session is a string
    app.logger.debug(f"load_user attempting for ID string: '{user_id_str}'")
    try:
        user_id_int = int(user_id_str)
        # For Flask-SQLAlchemy 3.x+ (likely installed if requirements.txt has >=2.5):
        user = db.session.get(User, user_id_int)
        if not user:
            app.logger.warning(f"load_user: No user found for ID {user_id_int}")
        return user
    except ValueError:
        app.logger.warning(f"load_user: Invalid user_id format '{user_id_str}'. Not an integer.")
        return None
    except Exception as e:
        app.logger.error(f"Error in load_user for ID string '{user_id_str}': {e}", exc_info=True)
        return None

# --- Question Data --- (Using your 30 questions)
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
        {"id": "rw2", "module": 1, "text": "Which of the following is a complete sentence? \n'Running through the park on a sunny day.'", "options": ["Yes, it is.", "No, it is a fragment.", "It depends on context.", "It is a command."], "correctAnswer": "No, it is a fragment.", "topic": "Standard English Conventions", "difficulty": "Easy"},
        {"id": "rw3", "module": 1, "text": "Choose the word that best completes the sentence: \n'The chef was known for his ______ use of spices, creating dishes that were both flavorful and unique.'", "options": ["sparing", "liberal", "excessive", "minimal"], "correctAnswer": "liberal", "topic": "Craft and Structure (Words in Context)", "difficulty": "Medium"},
        {"id": "rw4", "module": 1, "passage": "The city council debated the new proposal for public transportation. Proponents argued it would reduce traffic congestion, while opponents worried about the cost.", "text": "What is the main conflict described?", "options": ["Traffic vs. Pedestrians", "Cost vs. Benefit of new transport", "Council members' personal disagreements", "Old vs. New transportation methods"], "correctAnswer": "Cost vs. Benefit of new transport", "topic": "Information and Ideas", "difficulty": "Medium"},
        {"id": "rw5", "module": 1, "text": "Identify the grammatical error, if any: \n'Each of the students are responsible for their own materials.'", "options": ["'Each of the students'", "'are responsible'", "'their own materials'", "No error"], "correctAnswer": "'are responsible'", "topic": "Standard English Conventions (Subject-Verb Agreement)", "difficulty": "Medium"},
        {"id": "rw6", "module": 1, "text": "Which choice most effectively combines the sentences at the underlined portion? \n'The cat jumped. It landed softly on the mat.'", "options": ["jumped, it landed", "jumped and landed", "jumped, but it landed", "jumped; it landed"], "correctAnswer": "jumped and landed", "topic": "Expression of Ideas (Sentence Combining)", "difficulty": "Easy"},
        {"id": "rw7", "module": 1, "passage": "The scientist conducted many experiments. She hoped to find a cure for the disease. Her dedication was admirable.", "text": "The word 'admirable' in the last sentence most nearly means:", "options": ["questionable", "praiseworthy", "common", "ineffective"], "correctAnswer": "praiseworthy", "topic": "Craft and Structure (Words in Context)", "difficulty": "Easy"},
        {"id": "rw8", "module": 1, "text": "Which of the following sentences uses punctuation correctly? \n'The items needed are: eggs milk and bread.'", "options": ["The items needed are: eggs, milk, and bread.", "The items needed are eggs, milk, and bread.", "The items needed are, eggs, milk, and bread.", "The items needed are eggs milk and bread."], "correctAnswer": "The items needed are: eggs, milk, and bread.", "topic": "Standard English Conventions (Punctuation)", "difficulty": "Medium"},
        {"id": "rw9", "module": 1, "passage": "Many people believe that coffee provides an energy boost. However, excessive consumption can lead to negative side effects such as jitteriness and insomnia.", "text": "What is the primary purpose of the second sentence?", "options": ["To support the first sentence", "To contradict the first sentence", "To provide a solution", "To introduce a contrasting point"], "correctAnswer": "To introduce a contrasting point", "topic": "Information and Ideas (Purpose)", "difficulty": "Medium"},
        {"id": "rw10", "module": 1, "text": "Choose the correct pronoun: \n'Neither the teacher nor the students knew ______ way to the auditorium.'", "options": ["his", "her", "its", "their"], "correctAnswer": "their", "topic": "Standard English Conventions (Pronoun Agreement)", "difficulty": "Medium"},
        {"id": "rw11", "module": 1, "passage": "The invention of the printing press in the 15th century revolutionized the spread of information. Before its advent, books were painstakingly copied by hand, making them rare and expensive. The printing press allowed for mass production, making knowledge more accessible to a wider audience.", "text": "According to the passage, what was a primary consequence of the printing press?", "options": ["Books became more artistic.", "Fewer people learned to read.", "Information became more widespread.", "Hand-copying of books increased."], "correctAnswer": "Information became more widespread.", "topic": "Information and Ideas (Detail)", "difficulty": "Easy"},
        {"id": "rw12", "module": 1, "text": "Which word, if any, is misspelled in the following sentence? \n'She recieved a beautiful bouqet of flowers for her acheivement.'", "options": ["recieved", "bouqet", "acheivement", "No error"], "correctAnswer": "recieved", "topic": "Standard English Conventions (Spelling)", "difficulty": "Easy"},
        {"id": "rw13", "module": 1, "text": "The author implies that the main character's decision was: \n(Passage context needed for a real question - this is a placeholder for question type)", "options": ["Rash and impulsive", "Carefully considered", "Forced upon him", "Ultimately beneficial"], "correctAnswer": "Carefully considered", "topic": "Information and Ideas (Inference)", "difficulty": "Hard"},
        {"id": "rw14", "module": 1, "passage": "The artist's style was unique, characterized by bold colors and abstract shapes. Many critics praised her originality, though some found her work too unconventional.", "text": "The word 'unconventional' in this context means:", "options": ["Traditional", "Not conforming to accepted standards", "Widely popular", "Simple and plain"], "correctAnswer": "Not conforming to accepted standards", "topic": "Craft and Structure (Words in Context)", "difficulty": "Medium"},
        {"id": "rw15", "module": 1, "text": "Which sentence demonstrates the correct use of an apostrophe? \n'The dogs bowl was empty.'", "options": ["The dog's bowl was empty.", "The dogs' bowl was empty (if multiple dogs share one bowl).", "The dogs bowls were empty.", "Both A and B could be correct depending on context."], "correctAnswer": "Both A and B could be correct depending on context.", "topic": "Standard English Conventions (Apostrophes)", "difficulty": "Medium"},
        {"id": "rw16", "module": 1, "passage": "The documentary explored the impact of climate change on polar bear populations. It highlighted melting ice caps and the resulting loss of hunting grounds.", "text": "What is the main topic of the documentary described?", "options": ["Polar bear behavior", "The history of Arctic exploration", "The effects of climate change on polar bears", "Ice cap formation"], "correctAnswer": "The effects of climate change on polar bears", "topic": "Information and Ideas (Main Topic)", "difficulty": "Easy"},
        {"id": "rw17", "module": 1, "text": "The phrase 'to burn the midnight oil' means:", "options": ["To cause a fire late at night", "To work late into the night", "To waste resources", "To celebrate excessively"], "correctAnswer": "To work late into the night", "topic": "Craft and Structure (Idioms)", "difficulty": "Easy"},
        {"id": "rw18", "module": 1, "text": "Which sentence is grammatically correct? \n'Me and him went to the store.'", "options": ["Me and him went to the store.", "Him and I went to the store.", "He and I went to the store.", "I and he went to the store."], "correctAnswer": "He and I went to the store.", "topic": "Standard English Conventions (Pronoun Case)", "difficulty": "Medium"},
        {"id": "rw19", "module": 1, "passage": "The novel's protagonist is a young detective trying to solve a complex mystery. The author uses vivid imagery and suspenseful plot twists to keep the reader engaged.", "text": "What literary devices does the author use, according to the passage?", "options": ["Metaphor and simile", "Foreshadowing and irony", "Vivid imagery and suspenseful plot twists", "Alliteration and onomatopoeia"], "correctAnswer": "Vivid imagery and suspenseful plot twists", "topic": "Craft and Structure (Literary Devices)", "difficulty": "Medium"},
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
    user_id_log = current_user.id if current_user.is_authenticated else 'Anonymous (session init)'
    app.logger.info(f"Attempting to initialize test session for user: {user_id_log}")

    # Explicitly pop old test-related keys to ensure a completely fresh test state.
    keys_to_pop = ['current_question_index', 'answers', 'start_time', 'test_questions_ids_ordered', 'marked_for_review']
    for key in keys_to_pop:
        if session.pop(key, None): # Pop returns the value or None
             app.logger.debug(f"Popped old session key: {key} for user {user_id_log}")

    session['current_question_index'] = 0
    session['answers'] = {}
    session['start_time'] = datetime.datetime.now().isoformat() # This is CRUCIAL for the timer
    
    if not ORDERED_QUESTION_IDS:
        app.logger.error("CRITICAL FAILURE: ORDERED_QUESTION_IDS is empty during session initialization! No questions loaded from QUESTIONS_DATA.")
        raise ValueError("Cannot start test: No questions are available. Please check server configuration.")
    session['test_questions_ids_ordered'] = ORDERED_QUESTION_IDS[:]
    
    session['marked_for_review'] = {}
    session.modified = True # VERY IMPORTANT: Ensure Flask saves these session modifications.

    app.logger.info(f"Session successfully initialized for test for user {user_id_log}. "
                    f"Start time: {session.get('start_time')}, "
                    f"Num Qs ordered: {len(session.get('test_questions_ids_ordered', []))}. "
                    f"Current session keys present: {sorted(list(session.keys()))}")

def calculate_mock_score(answers):
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
    else: weaknesses.append("No questions processed."); recommendations.append("Check test configuration.")
    return {"total_score": mock_total_score, "math_score": mock_math_score, "rw_score": mock_rw_score, "correct_count": correct_count, "total_answered": len(answers), "total_test_questions": TOTAL_QUESTIONS, "weaknesses": weaknesses, "recommendations": recommendations}

def generate_csv_report(score_obj):
    output = io.StringIO(); writer = csv.writer(output)
    headers = ["Question Number", "Section", "Skill Type", "Your Answer", "Correct Answer", "Outcome", "QuestionID", "Module", "Difficulty", "QuestionText", "AllOptions", "ScoreID", "TestDate"]
    writer.writerow(headers)
    if not score_obj or not score_obj.answers_data: writer.writerow(["N/A"] * len(headers[:-2]) + [score_obj.id if score_obj else "N/A", "N/A"]); output.seek(0); return output.getvalue()
    try: user_answers_dict = json.loads(score_obj.answers_data)
    except json.JSONDecodeError: writer.writerow(["Error decoding answers"] + ["N/A"] * (len(headers) - 3) + [score_obj.id, score_obj.timestamp.strftime('%Y-%m-%d %H:%M:%S') if score_obj.timestamp else "N/A"]); output.seek(0); return output.getvalue()
    test_date_str = score_obj.timestamp.strftime('%Y-%m-%d %H:%M:%S') if score_obj.timestamp else "N/A"
    for idx, q_id in enumerate(ORDERED_QUESTION_IDS):
        question_detail = ALL_QUESTIONS_MAP.get(q_id); question_sequence_number = idx + 1
        if not question_detail: writer.writerow([question_sequence_number, "Unknown", "N/A", "N/A", "N/A", "Question Detail Missing", q_id, "N/A", "N/A", f"Details missing for Q_ID: {q_id}", "[]", score_obj.id, test_date_str]); continue
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
    return render_template("error_page.html", error_code=500, error_name="Internal Server Error", error_message="An unexpected internal error occurred. We've been notified and are looking into it."), 500

# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html', total_questions=TOTAL_QUESTIONS, duration=TEST_DURATION_MINUTES, now=datetime.datetime.utcnow())

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password')
        if not username or not password: flash('Username and password are required.', 'warning'); return redirect(url_for('register'))
        if len(username) < 3: flash('Username must be at least 3 characters.', 'warning'); return redirect(url_for('register'))
        if len(password) < 6: flash('Password must be at least 6 characters.', 'warning'); return redirect(url_for('register'))
        
        existing_user = User.query.filter_by(username=username).first()
        if existing_user: flash('Username already exists.', 'danger'); return redirect(url_for('register'))
        
        new_user = User(username=username)
        new_user.set_password(password)
        try:
            db.session.add(new_user); db.session.commit()
            flash('Registration successful! Please log in.', 'success'); app.logger.info(f"User '{username}' registered.")
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"DB error during registration for '{username}': {e}", exc_info=True)
            flash('Database error during registration. Please try again.', 'danger')
            return redirect(url_for('register'))
    return render_template('register.html', now=datetime.datetime.utcnow())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first() # Case-sensitive username
        if user and user.check_password(password):
            login_user(user, remember=(request.form.get('remember') == 'on'))
            flash('Logged in successfully!', 'success');
            app.logger.info(f"User '{username}' logged in.")
            next_page = request.args.get('next')
            # Basic Open Redirect protection
            if next_page and not (next_page.startswith('/') or next_page.startswith(request.host_url)):
                 app.logger.warning(f"Invalid 'next' URL '{next_page}' during login for user '{username}'. Defaulting to index.")
                 next_page = url_for('index')
            return redirect(next_page or url_for('index'))
        else:
            flash('Invalid username or password.', 'danger')
            app.logger.warning(f"Failed login for username '{username}'.")
    return render_template('login.html', now=datetime.datetime.utcnow())

@app.route('/logout')
@login_required
def logout():
    user_id_log = current_user.username
    logout_user()
    session.clear() # Clear the entire session for a clean logout
    flash('You have been successfully logged out.', 'info')
    app.logger.info(f"User '{user_id_log}' logged out and session cleared.")
    return redirect(url_for('index'))

@app.route('/dashboard/')
@login_required
def dashboard():
    app.logger.info(f"Dashboard accessed by user: '{current_user.username}'")
    try:
        user_scores = current_user.scores.order_by(Score.timestamp.desc()).all()
    except Exception as e:
        app.logger.error(f"Database error fetching scores for dashboard for user '{current_user.username}': {e}", exc_info=True)
        flash('Could not retrieve your scores due to a server error.', 'danger')
        user_scores = []
    return render_template('dashboard.html', scores=user_scores, now=datetime.datetime.utcnow())

@app.route('/start_test', methods=['POST'])
@login_required
def start_test():
    user_id_log = current_user.username
    app.logger.info(f"User '{user_id_log}' is POSTing to /start_test to initialize a new test.")
    try:
        initialize_test_session()
        app.logger.info(f"Test session successfully initialized for '{user_id_log}'. Redirecting to first question (q_idx=0).")
        return redirect(url_for('test_question_page', q_idx=0))
    except ValueError as ve:
        app.logger.error(f"ValueError during start_test for user '{user_id_log}': {ve}", exc_info=True)
        flash(str(ve), "danger")
        return redirect(url_for('index'))
    except Exception as e:
        app.logger.error(f"Unexpected error during /start_test for user '{user_id_log}': {e}", exc_info=True)
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
    
    if session_valid and (not session.get('test_questions_ids_ordered') or len(session.get('test_questions_ids_ordered',[])) == 0) :
        session_valid = False
        app.logger.error(f"SESSION INVALID for '{user_id_log}' at q_idx {q_idx}. 'test_questions_ids_ordered' is empty/None or has zero length. Session content: {dict(session)}")

    if not session_valid:
        flash('Your test session is invalid or appears to have expired. Please start a new test to continue.', 'warning')
        return redirect(url_for('index'))

    ordered_ids = session['test_questions_ids_ordered']
    
    if not (0 <= q_idx < len(ordered_ids)):
        valid_q_idx = session.get('current_question_index', 0)
        if not (0 <= valid_q_idx < len(ordered_ids)) and len(ordered_ids) > 0 :
             valid_q_idx = 0 
        elif len(ordered_ids) == 0: 
            app.logger.error(f"Critical error: No questions in session for user '{user_id_log}' and q_idx {q_idx} is out of bounds. Redirecting to index.")
            flash('No questions found in the current test session. Please try starting a new test.', 'danger')
            return redirect(url_for('index')) 

        flash('Invalid question number. Redirecting to your current or first question.', 'danger')
        app.logger.warning(f"Out-of-bounds q_idx {q_idx} (max: {len(ordered_ids)-1}) for user '{user_id_log}'. Redirecting to {valid_q_idx}.")
        return redirect(url_for('test_question_page', q_idx=valid_q_idx))
    
    session['current_question_index'] = q_idx
    question_id = ordered_ids[q_idx]
    question = ALL_QUESTIONS_MAP.get(question_id)

    if not question:
        flash('Error: Question data could not be loaded. Please restart the test.', 'danger')
        app.logger.error(f"Question ID '{question_id}' (index {q_idx}) NOT FOUND in ALL_QUESTIONS_MAP for '{user_id_log}'.")
        return redirect(url_for('index'))

    if request.method == 'POST':
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
    if 'answers' not in session or 'start_time' not in session: flash('Test data incomplete. Start new test.', 'warning'); return redirect(url_for('index'))
    user_submitted_answers = session.get('answers', {}); start_time_iso = session.get('start_time')
    if not start_time_iso: flash('Error: Test start time missing.', 'danger'); return redirect(url_for('index'))
    try: start_time = datetime.datetime.fromisoformat(start_time_iso)
    except: flash('Error with test start time format.', 'danger'); return redirect(url_for('index'))
    
    end_time = datetime.datetime.now(datetime.timezone.utc)
    if start_time.tzinfo is None: start_time = start_time.replace(tzinfo=datetime.timezone.utc)
    else: start_time = start_time.astimezone(datetime.timezone.utc)
    time_taken_seconds = (end_time - start_time).total_seconds()

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
    """Creates database tables from models if they don't exist."""
    try:
        with app.app_context():
            app.logger.info("Executing 'flask init-db': Attempting to create database tables...")
            db.create_all()
        app.logger.info("'flask init-db' executed successfully: Database tables checked/created.")
        print("Initialized the database: Tables checked/created.")
    except Exception as e:
        error_message = f"Error during 'flask init-db' command: {e}"
        print(error_message)
        app.logger.error(error_message, exc_info=True)

if __name__ == '__main__':
    app.logger.info(f"Starting Flask development server (Debug: {is_debug_env}). Listening on http://{os.environ.get('HOST', '0.0.0.0')}:{os.environ.get('PORT', 5000)}")
    # db.create_all() was in your original code. For local dev, it's often fine if the DB file doesn't exist.
    # For production or more controlled setup, `flask init-db` is preferred.
    # If you keep this, ensure it's within app_context for safety if app is not yet fully configured.
    if is_debug_env: # Only consider this for local debug convenience
        with app.app_context():
             db.create_all() # This will create tables if they don't exist.
    app.run(host=os.environ.get('HOST', '0.0.0.0'), 
            port=int(os.environ.get('PORT', 5000)))
