from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
import datetime
import io # Removed 'random' as it wasn't used in your provided code
import csv
import json
import logging

# --- Application Setup ---
app = Flask(__name__)

# --- Logging Setup ---
is_debug_env = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
log_level = logging.DEBUG if is_debug_env else logging.INFO
app.logger.setLevel(log_level)
# Basic configuration for logging to console
logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s %(name)s: %(message)s')

if not is_debug_env:
    app.logger.info('SATInsight App Starting Up in Production-like mode (e.g., on Render)')
else:
    app.logger.info('SATInsight App Starting Up in DEBUG mode (local development)')

# --- SECRET_KEY Configuration ---
# CRITICAL FOR RENDER: 'SECRET_KEY' MUST be set in your Render service's Environment Variables.
# Using os.urandom() as a direct assignment here IS THE PRIMARY CAUSE OF YOUR RELOADING ISSUES ON RENDER.
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') # Try to get it from environment first
if not app.config['SECRET_KEY']:
    app.logger.critical("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    app.logger.critical("!!! FATAL ERROR: SECRET_KEY ENVIRONMENT VARIABLE IS NOT SET                 !!!")
    app.logger.critical("!!! Flask sessions WILL FAIL, leading to app crashes and reload loops.    !!!")
    app.logger.critical("!!! SET THIS IN YOUR RENDER SERVICE ENVIRONMENT SETTINGS IMMEDIATELY.     !!!")
    app.logger.critical("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    if is_debug_env: # Fallback for local development ONLY if FLASK_DEBUG is true
        app.logger.warning("DEVELOPMENT ONLY: Using an INSECURE os.urandom() for SECRET_KEY because it was not set via env.")
        app.logger.warning("This key will change on each app restart, breaking sessions even locally.")
        app.config['SECRET_KEY'] = os.urandom(24) # For local dev, better to use a fixed string or .env file
    else:
        # In a production-like environment (not debug), if SECRET_KEY is still not set,
        # it's a critical misconfiguration. The app will crash on session use.
        # Flask will raise a RuntimeError later when session is accessed.
        pass

# --- Database Configuration ---
# CRITICAL FOR RENDER: 'DATABASE_URL' MUST be set in Render Environment Variables for PostgreSQL.
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    app.logger.info(f"DATABASE_URL detected from environment. Type: {DATABASE_URL.split('://')[0] if '://' in DATABASE_URL else 'Unknown'}")
    if DATABASE_URL.startswith("postgres://"): # Common for Heroku-like services including Render
        app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        app.logger.info("Adjusted DATABASE_URL for SQLAlchemy (postgres:// -> postgresql://).")
    elif DATABASE_URL.startswith("postgresql://"):
        app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
        app.logger.info("Using standard PostgreSQL DATABASE_URL.")
    else: # For other DBs or if the URL is already in SQLAlchemy format
        app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
        app.logger.info(f"Using provided DATABASE_URL as is for other DB type: {app.config['SQLALCHEMY_DATABASE_URI']}")
else:
    app.logger.warning("DATABASE_URL environment variable NOT FOUND. Defaulting to local SQLite ('sqlite:///sattest.db').")
    app.logger.warning("IMPORTANT: For Render deployment, SQLite is NOT recommended for persistent data due to its ephemeral filesystem. "
                     "Data (users, scores) WILL BE LOST on deploys/restarts. Use Render's managed PostgreSQL service and set DATABASE_URL.")
    # For local SQLite, ensure the instance folder exists if you use app.instance_path
    # Your original code uses a relative path, which will create sattest.db in the root if instance_path is not used.
    # For more robust local SQLite:
    # instance_path = os.path.join(app.instance_path)
    # if not os.path.exists(instance_path): os.makedirs(instance_path, exist_ok=True)
    # sqlite_db_file = os.path.join(instance_path, 'sattest.db')
    # app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + sqlite_db_file
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///sattest.db' # As per your original code for fallback
    app.logger.info(f"SQLite database configured at: {app.config['SQLALCHEMY_DATABASE_URI']}")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = 'info'

# --- Database Models --- (Copied from your provided code)
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    scores = db.relationship('Score', backref='user', lazy='dynamic') # Changed to dynamic for potentially large lists

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
def load_user(user_id_str): # Renamed from 'user_id' to 'user_id_str' to emphasize it's a string
    app.logger.debug(f"load_user attempting for ID string: '{user_id_str}'")
    try:
        user_id_int = int(user_id_str)
        # For Flask-SQLAlchemy 3.x+ (likely installed by >=2.5), use db.session.get
        user = db.session.get(User, user_id_int)
        # For older versions: user = User.query.get(user_id_int)
        if not user:
            app.logger.warning(f"load_user: No user found for ID {user_id_int}")
        return user
    except ValueError: # If user_id_str is not a valid integer
        app.logger.warning(f"load_user: Invalid user_id format '{user_id_str}'. Not an integer.")
        return None
    except Exception as e: # Catch any other unexpected errors
        app.logger.error(f"Error in load_user for ID string '{user_id_str}': {e}", exc_info=True)
        return None

# --- Question Data --- (Using your provided 30 questions)
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
TEST_DURATION_MINUTES = 30 # This sets the duration for the timer
app.logger.info(f"Successfully loaded {TOTAL_QUESTIONS} questions ({len(QUESTIONS_DATA['math'])} Math, {len(QUESTIONS_DATA['reading_writing'])} R&W).")

def initialize_test_session():
    user_id_log = current_user.id if current_user.is_authenticated else 'Anonymous (User not authenticated during session init)'
    app.logger.info(f"Attempting to initialize test session for user: {user_id_log}")

    # Explicitly pop old test-related keys to ensure a clean state for the new test.
    keys_to_pop = ['current_question_index', 'answers', 'start_time', 'test_questions_ids_ordered', 'marked_for_review']
    for key in keys_to_pop:
        session.pop(key, None)
    # No need for session.modified = True after only pops if new items are immediately set.

    session['current_question_index'] = 0
    session['answers'] = {}
    session['start_time'] = datetime.datetime.now().isoformat() # Crucial for timer
    
    if not ORDERED_QUESTION_IDS: # Check if questions actually loaded
        app.logger.error("CRITICAL FAILURE: ORDERED_QUESTION_IDS is empty during session initialization! This means no questions were loaded from QUESTIONS_DATA.")
        # This situation should ideally not occur if QUESTIONS_DATA is populated.
        # Raising an error here will stop the test start process, which is better than proceeding with no questions.
        raise ValueError("Cannot start test: No questions are available. Please check server configuration or question data.")
    session['test_questions_ids_ordered'] = ORDERED_QUESTION_IDS[:] # Store a copy of the ordered IDs
    
    session['marked_for_review'] = {}
    session.modified = True # Crucial to ensure the session is saved after these modifications

    # Log the state of the session after initialization for debugging
    app.logger.info(f"Session successfully initialized for test for user {user_id_log}. "
                    f"Start time: {session.get('start_time')}, "
                    f"Num Qs ordered: {len(session.get('test_questions_ids_ordered', []))}. "
                    f"Current session keys present: {sorted(list(session.keys()))}")


def calculate_mock_score(answers):
    # ... (This function seemed fine from your version, ensure it's robust) ...
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
    if TOTAL_QUESTIONS > 0: # Check if there were questions to begin with
        if math_total_qs_in_test > 0 and (math_correct / math_total_qs_in_test) < 0.6: weaknesses.append("Math Concepts"); recommendations.append("Review math topics.")
        if rw_total_qs_in_test > 0 and (rw_correct / rw_total_qs_in_test) < 0.6: weaknesses.append("R&W Skills"); recommendations.append("Focus on R&W techniques.")
        if not weaknesses: weaknesses.append("Good performance!"); recommendations.append("Keep practicing.")
    else: weaknesses.append("No questions processed."); recommendations.append("Check test configuration.")
    return {"total_score": mock_total_score, "math_score": mock_math_score, "rw_score": mock_rw_score, "correct_count": correct_count, "total_answered": len(answers), "total_test_questions": TOTAL_QUESTIONS, "weaknesses": weaknesses, "recommendations": recommendations}

def generate_csv_report(score_obj):
    # ... (This function seemed fine, ensure robustness for missing data) ...
    output = io.StringIO(); writer = csv.writer(output)
    headers = ["Question Number", "Section", "Skill Type", "Your Answer", "Correct Answer", "Outcome", "QuestionID", "Module", "Difficulty", "QuestionText", "AllOptions", "ScoreID", "TestDate"]
    writer.writerow(headers)
    if not score_obj or not score_obj.answers_data: # Ensure score_obj itself is not None
        writer.writerow(["N/A"] * len(headers[:-2]) + [score_obj.id if score_obj else "N/A", "N/A"])
        output.seek(0); return output.getvalue()
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
def page_not_found_error_handler(e): # Renamed to avoid conflict with other 'e'
    user_id_log = current_user.id if current_user.is_authenticated else 'Anonymous'
    app.logger.warning(f"404 Not Found: {request.url} (Referrer: {request.referrer}) by user {user_id_log}")
    return render_template('error_page.html', error_code=404, error_name="Page Not Found", error_message="The page you were looking for doesn't exist."), 404

@app.errorhandler(Exception)
def handle_general_exception_handler(e): # Renamed to avoid conflict
    app.logger.error(f"Unhandled application exception: {e} at {request.url}", exc_info=True)
    from werkzeug.exceptions import HTTPException # Import locally
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
        # Add more validation (e.g., length)
        if not username or not password: flash('Username and password are required.', 'warning'); return redirect(url_for('register'))
        if len(username) < 3: flash('Username must be at least 3 characters long.', 'warning'); return redirect(url_for('register'))
        if len(password) < 6: flash('Password must be at least 6 characters long.', 'warning'); return redirect(url_for('register'))
        
        if User.query.filter_by(username=username).first(): # Check if user exists
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
        except Exception as e: # Catch DB errors
            db.session.rollback()
            app.logger.error(f"Database error during registration for '{username}': {e}", exc_info=True)
            flash('An error occurred during registration. Please try again later.', 'danger')
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
            flash('Logged in successfully!', 'success')
            app.logger.info(f"User '{username}' logged in successfully.")
            next_page = request.args.get('next')
            # Basic Open Redirect protection
            if next_page and not (next_page.startswith('/') or next_page.startswith(request.host_url)):
                 app.logger.warning(f"Invalid 'next' URL '{next_page}' provided during login for user '{username}'. Defaulting to index.")
                 next_page = url_for('index')
            return redirect(next_page or url_for('index'))
        else:
            flash('Invalid username or password.', 'danger')
            app.logger.warning(f"Failed login attempt for username: '{username}'")
    return render_template('login.html', now=datetime.datetime.utcnow())

@app.route('/logout')
@login_required
def logout():
    user_id_log = current_user.username # Get username before logout
    logout_user()
    session.clear() # Clear the entire session to ensure all test data is gone
    flash('You have been successfully logged out.', 'info')
    app.logger.info(f"User '{user_id_log}' logged out and session cleared.")
    return redirect(url_for('index'))

@app.route('/dashboard/') # Added trailing slash for consistency if other routes have it
@login_required
def dashboard():
    app.logger.info(f"Dashboard accessed by user: '{current_user.username}'")
    try:
        user_scores = current_user.scores.order_by(Score.timestamp.desc()).all()
    except Exception as e:
        app.logger.error(f"Database error on dashboard for user '{current_user.username}': {e}", exc_info=True)
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
        # Log inside initialize_test_session confirms session state
        app.logger.info(f"Test session successfully initialized for '{user_id_log}'. Redirecting to first question (q_idx=0).")
        return redirect(url_for('test_question_page', q_idx=0))
    except ValueError as ve: # Catch specific error from initialize_test_session if no questions
        app.logger.error(f"ValueError during start_test for user '{user_id_log}': {ve}", exc_info=True)
        flash(str(ve), "danger") # Show the specific error (e.g., "No questions available")
        return redirect(url_for('index'))
    except Exception as e: # Catch any other unexpected errors
        app.logger.error(f"Unexpected error during /start_test for user '{user_id_log}': {e}", exc_info=True)
        flash("An unexpected server error occurred while trying to start the test. Please try again.", "danger")
        return redirect(url_for('index'))

@app.route('/test/question/<int:q_idx>', methods=['GET', 'POST'])
@login_required
def test_question_page(q_idx):
    user_id_log = current_user.username
    app.logger.info(f"Accessing /test/question/{q_idx} for user '{user_id_log}'. Method: {request.method}.")
    app.logger.debug(f"Current session keys for '{user_id_log}': {sorted(list(session.keys()))}")
    app.logger.debug(f"Session 'test_questions_ids_ordered' length: {len(session.get('test_questions_ids_ordered', []))}, 'start_time': {session.get('start_time')}")

    # Robust check for valid test session
    required_session_keys = ['test_questions_ids_ordered', 'answers', 'start_time', 'marked_for_review', 'current_question_index']
    session_valid = True
    missing_keys = [key for key in required_session_keys if key not in session]

    if missing_keys:
        session_valid = False
        app.logger.error(f"SESSION INVALID for '{user_id_log}' at q_idx {q_idx}. Missing session keys: {missing_keys}. Session content: {dict(session)}")
    
    # Also check if the list of ordered questions is actually populated in the session
    if session_valid and (not session.get('test_questions_ids_ordered') or len(session.get('test_questions_ids_ordered',[])) == 0) :
        session_valid = False
        app.logger.error(f"SESSION INVALID for '{user_id_log}' at q_idx {q_idx}. 'test_questions_ids_ordered' is empty/None or has zero length. Session content: {dict(session)}")

    if not session_valid:
        flash('Your test session is invalid or appears to have expired. Please start a new test to continue.', 'warning')
        return redirect(url_for('index'))

    ordered_ids = session['test_questions_ids_ordered'] # We know this key exists and list is not empty if session_valid
    
    # Boundary check for q_idx
    if not (0 <= q_idx < len(ordered_ids)):
        # If q_idx is out of bounds, try to redirect to a known valid index or the start.
        valid_q_idx = session.get('current_question_index', 0)
        if not (0 <= valid_q_idx < len(ordered_ids)): # If stored current_question_index is also bad
            valid_q_idx = 0 # Default to the very first question
        flash('Invalid question number requested. Redirecting appropriately.', 'danger')
        app.logger.warning(f"Out-of-bounds q_idx {q_idx} (max index: {len(ordered_ids)-1}) for user '{user_id_log}'. Redirecting to {valid_q_idx}.")
        return redirect(url_for('test_question_page', q_idx=valid_q_idx))
    
    session['current_question_index'] = q_idx # Update current index
    question_id = ordered_ids[q_idx]
    question = ALL_QUESTIONS_MAP.get(question_id)

    if not question: # Should be rare if ORDERED_QUESTION_IDS and ALL_QUESTIONS_MAP are consistent
        flash('Error: Question data could not be loaded for this question. The test structure might be corrupted. Please restart the test.', 'danger')
        app.logger.error(f"Question ID '{question_id}' (index {q_idx}) NOT FOUND in ALL_QUESTIONS_MAP for user '{user_id_log}'.")
        # initialize_test_session() # Avoid initializing here as it might hide the root cause or loop if the cause is persistent.
        return redirect(url_for('index')) # Safer to send to index to allow a clean restart attempt by user.

    if request.method == 'POST':
        # Update answer if provided
        selected_option = request.form.get('answer')
        if selected_option:
            session['answers'][question_id] = selected_option
        
        # Update mark_for_review status
        if 'mark_review' in request.form and request.form.get('mark_review') == 'true':
            session['marked_for_review'][question_id] = True
        else: # Checkbox not submitted (i.e., unchecked) or value not 'true'
            session['marked_for_review'].pop(question_id, None) # Remove if it exists, do nothing if not
        
        session.modified = True # Ensure changes are saved

        action = request.form.get('action') # From hidden 'Next'/'Back' buttons
        if action == 'next':
            if q_idx + 1 < len(ordered_ids):
                return redirect(url_for('test_question_page', q_idx=q_idx + 1))
            else: # Last question, go to results
                return redirect(url_for('results'))
        elif action == 'back':
            if q_idx > 0:
                return redirect(url_for('test_question_page', q_idx=q_idx - 1))
            # If on first question and 'back' is somehow triggered, stay on first question
        
        # If no specific 'action' (e.g., form submitted by 'Mark for Review' checkbox change),
        # redirect to the current question page to reflect changes.
        return redirect(url_for('test_question_page', q_idx=q_idx))

    # GET request: Display the question
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
    if 'answers' not in session or 'start_time' not in session: # Check essential keys
        flash('Test data is incomplete or your session has expired. Please start a new test.', 'warning')
        return redirect(url_for('index'))

    user_submitted_answers = session.get('answers', {}) # Default to empty dict
    start_time_iso = session.get('start_time')

    if not start_time_iso: # Should not happen if previous check passed
        flash('Critical error: Test start time missing from session. Cannot calculate results. Please restart.', 'danger')
        app.logger.error(f"Results page: 'start_time' is None/empty in session for user '{current_user.username}'.")
        return redirect(url_for('index'))

    try:
        start_time = datetime.datetime.fromisoformat(start_time_iso)
    except (ValueError, TypeError) as e:
        app.logger.error(f"Invalid 'start_time' format ('{start_time_iso}') for user '{current_user.username}': {e}", exc_info=True)
        flash('There was an error processing your test start time. Results might be affected. Please start a new test.', 'danger')
        return redirect(url_for('index'))

    end_time = datetime.datetime.now(datetime.timezone.utc) # Use timezone-aware now for end_time
    # Ensure start_time is also timezone-aware or naive consistently for subtraction
    if start_time.tzinfo is None:
        start_time_aware = start_time.replace(tzinfo=datetime.timezone.utc) # Assume UTC if naive
    else:
        start_time_aware = start_time.astimezone(datetime.timezone.utc) # Convert to UTC if already aware
    
    time_taken_seconds = (end_time - start_time_aware).total_seconds()
    
    results_summary = calculate_mock_score(user_submitted_answers)
    results_summary['time_taken_formatted'] = f"{int(time_taken_seconds // 60)}m {int(time_taken_seconds % 60)}s"
    
    answers_json_string = json.dumps(user_submitted_answers)
    score_id_for_template = None
    try:
        new_score = Score(user_id=current_user.id,
                          total_score=results_summary['total_score'], math_score=results_summary['math_score'],
                          rw_score=results_summary['rw_score'], correct_count=results_summary['correct_count'],
                          total_answered=results_summary['total_answered'], answers_data=answers_json_string,
                          timestamp=end_time) # Use server's end_time (UTC)
        db.session.add(new_score)
        db.session.commit()
        score_id_for_template = new_score.id
        app.logger.info(f"Score (ID: {new_score.id}) saved for user '{current_user.username}'.")
        flash('Your test results have been successfully saved!', 'success')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Database error while saving score for user '{current_user.username}': {e}", exc_info=True)
        flash('A database error occurred while saving your score. Please try submitting again or contact support.', 'danger')

    # Clean up test-specific session data after saving results
    session_keys_to_pop = ['current_question_index', 'answers', 'start_time', 
                           'test_questions_ids_ordered', 'marked_for_review']
    for key in session_keys_to_pop:
        session.pop(key, None)
    session.modified = True
        
    return render_template('results_page.html', results=results_summary, score_id=score_id_for_template, now=datetime.datetime.utcnow())

@app.route('/download_report/<int:score_id>/<string:report_format>')
@login_required
def download_report(score_id, report_format):
    score_to_download = db.session.get(Score, score_id) # SQLAlchemy 3.x style
    if not score_to_download:
        flash(f"Score report with ID {score_id} not found.", "danger")
        return redirect(request.referrer or url_for('dashboard'))
    if score_to_download.user_id != current_user.id:
        flash("You do not have permission to access this score report.", "danger")
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
            flash("Could not generate the CSV report at this time.", "danger")
            return redirect(request.referrer or url_for('dashboard'))
    else:
        flash(f"Unsupported report format requested: {report_format}.", "warning")
        return redirect(request.referrer or url_for('dashboard'))

@app.route('/reset_test', methods=['POST'])
@login_required
def reset_test():
    app.logger.info(f"User '{current_user.username}' manually resetting test session via POST.")
    keys_to_pop = ['current_question_index', 'answers', 'start_time', 
                   'test_questions_ids_ordered', 'marked_for_review']
    for key in keys_to_pop:
        session.pop(key, None)
    session.modified = True
    flash('Your test session has been reset. You can start a new test.', 'info')
    return redirect(url_for('index'))

@app.cli.command("init-db")
def init_db_command():
    """Creates database tables from models if they don't exist."""
    try:
        with app.app_context():
            app.logger.info("Executing 'flask init-db': Attempting to create database tables...")
            db.create_all() # Creates tables based on models if they don't exist
        app.logger.info("'flask init-db' executed successfully: Database tables checked/created.")
        print("Initialized the database: Tables checked/created.")
    except Exception as e:
        # Also log to Flask logger if available and configured
        app.logger.error(f"Error during 'flask init-db' command: {e}", exc_info=True)
        print(f"Error during 'flask init-db' command: {e}")


# This block runs when you execute `python app.py` directly (for local development)
# For Render, Gunicorn is the entry point defined in your Procfile (e.g., web: gunicorn app:app)
if __name__ == '__main__':
    # The 'debug' flag for app.run is controlled by FLASK_DEBUG env var.
    # is_debug_env is already defined at the top based on this.
    app.logger.info(f"Starting Flask development server (Debug: {is_debug_env}). "
                  f"Listening on http://{os.environ.get('HOST', '0.0.0.0')}:{os.environ.get('PORT', 5000)}")
    
    # For local development, you might want to ensure tables are created on first run if not using `flask init-db`.
    # However, `flask init-db` is a cleaner approach.
    # if is_debug_env:
    #     with app.app_context():
    #         db.create_all()
    
    app.run(host=os.environ.get('HOST', '0.0.0.0'), 
            port=int(os.environ.get('PORT', 5000)))
