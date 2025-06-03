from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, jsonify # Ensure jsonify is imported
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
import datetime
import io
import csv
import json

# --- Application Setup ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///sattest.db' # As per original file
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

# --- Question Data (Full Original Set) ---
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
TEST_DURATION_MINUTES = 30 # Example duration from original file

def initialize_test_session():
    session['current_question_index'] = 0
    session['answers'] = {}
    session['start_time'] = datetime.datetime.now().isoformat()
    session['test_questions_ids_ordered'] = ORDERED_QUESTION_IDS[:] # Ensure a copy is used
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
        is_math = any(q_id == m_q['id'] for m_q in QUESTIONS_DATA.get('math', []))
        if is_math: math_total += 1
        else: rw_total += 1
        if user_answer == question_detail['correctAnswer']:
            correct_count += 1
            if is_math: math_correct += 1
            else: rw_correct += 1
    
    math_score_ratio = (math_correct / max(1, math_total)) if math_total > 0 else 0
    rw_score_ratio = (rw_correct / max(1, rw_total)) if rw_total > 0 else 0
        
    mock_math_score = 200 + int(math_score_ratio * 600)
    mock_rw_score = 200 + int(rw_score_ratio * 600)
    
    mock_math_score = max(200, min(800, mock_math_score))
    mock_rw_score = max(200, min(800, mock_rw_score))
    
    mock_total_score = mock_math_score + mock_rw_score
    mock_total_score = max(400, min(1600, mock_total_score))

    weaknesses = []
    recommendations = []
    if math_total > 0 and math_score_ratio < 0.6: 
        weaknesses.append("Algebra Concepts (Math)")
        recommendations.append("Review foundational algebra topics.")
    if rw_total > 0 and rw_score_ratio < 0.6: 
        weaknesses.append("Grammar Rules (Reading & Writing)")
        recommendations.append("Focus on Standard English Conventions.")
    
    if not weaknesses and (math_total > 0 or rw_total > 0) :
        recommendations.append("Continue practicing across all topics to maintain your skills.")
    elif not weaknesses and math_total == 0 and rw_total == 0:
        weaknesses.append("No answers to analyze.")
        recommendations.append("Complete the test to get a performance analysis.")

    return {
        "total_score": mock_total_score, 
        "math_score": mock_math_score, 
        "rw_score": mock_rw_score, 
        "correct_count": correct_count, 
        "total_answered": len(answers), 
        "weaknesses": weaknesses, 
        "recommendations": recommendations
    }

def generate_csv_report(score_obj):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Question Number", "Section", "Skill Type", "Your Answer", "Correct Answer", "Outcome",
        "QuestionID", "Module", "Difficulty", "QuestionText", "AllOptions", "ScoreID", "TestDate"
    ])
    if not score_obj or not score_obj.answers_data: # Added check for score_obj itself
        writer.writerow([
            "N/A", "N/A", "N/A", "N/A", "N/A", "No detailed answer data" if score_obj else "Score object missing",
            "N/A", "N/A", "N/A", "N/A", "N/A", score_obj.id if score_obj else "N/A",
            score_obj.timestamp.strftime('%Y-%m-%d %H:%M:%S') if score_obj and score_obj.timestamp else "N/A"
        ])
        output.seek(0)
        return output.getvalue()
    try:
        user_answers_dict = json.loads(score_obj.answers_data)
    except json.JSONDecodeError:
        writer.writerow([
            "N/A", "N/A", "N/A", "N/A", "N/A", "Error decoding answers",
            "N/A", "N/A", "N/A", "N/A", "N/A", score_obj.id,
            score_obj.timestamp.strftime('%Y-%m-%d %H:%M:%S') if score_obj.timestamp else "N/A"
        ])
        output.seek(0)
        return output.getvalue()

    test_date_str = score_obj.timestamp.strftime('%Y-%m-%d %H:%M:%S') if score_obj.timestamp else "N/A"
    score_id_val = score_obj.id
    question_sequence_number = 0

    current_ordered_ids = ORDERED_QUESTION_IDS # Use the global one; ensure it's current if test structure can change

    for q_id in current_ordered_ids:
        question_sequence_number += 1
        question_detail = ALL_QUESTIONS_MAP.get(q_id)
        if not question_detail:
            writer.writerow([
                question_sequence_number, "Unknown", "Unknown", "N/A", "N/A", "Question detail missing",
                q_id, "Unknown", "Unknown", f"Details not found for Q_ID: {q_id}",
                "[]", score_id_val, test_date_str
            ])
            continue
        
        section_val = "Math" if any(q_id == m_q['id'] for m_q in QUESTIONS_DATA.get('math', [])) else "Reading & Writing"
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
             question_text_val = f"[PASSAGE:{passage_text[:20]}...] {question_text_val}" # Truncate passage for CSV
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
        if not username or not password: # Basic validation
            flash('Username and password are required.', 'warning')
            return redirect(url_for('register'))
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose a different one.', 'danger')
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
            login_user(user, remember=request.form.get('remember') == 'on') # Handle remember me
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

@app.route('/dashboard')
@login_required
def dashboard():
    user_scores = Score.query.filter_by(user_id=current_user.id).order_by(Score.timestamp.desc()).all()
    return render_template('dashboard.html', scores=user_scores, now=datetime.datetime.utcnow())

@app.route('/start_test', methods=['POST'])
@login_required
def start_test():
    initialize_test_session()
    return redirect(url_for('test_question_page', q_idx=0))

@app.route('/update_mark_review_status', methods=['POST'])
@login_required
def update_mark_review_status():
    print("--- /update_mark_review_status CALLED ---") # DEBUG
    if 'test_questions_ids_ordered' not in session:
        print("DEBUG: Test session not found in /update_mark_review_status") # DEBUG
        return jsonify(success=False, error="Test session not found"), 400
        
    data = request.get_json()
    print(f"DEBUG: Received data for mark_review: {data}") # DEBUG
    if not data:
        print("DEBUG: No data received in /update_mark_review_status") # DEBUG
        return jsonify(success=False, error="No data received"), 400

    question_id = data.get('question_id')
    is_marked = data.get('mark_review')

    if question_id is None or not isinstance(is_marked, bool):
        print(f"DEBUG: Invalid data in /update_mark_review_status: q_id={question_id}, is_marked={is_marked}") # DEBUG
        return jsonify(success=False, error="Invalid data: question_id or mark_review status missing/invalid"), 400

    ordered_ids = session.get('test_questions_ids_ordered', [])
    if question_id not in ordered_ids:
        print(f"DEBUG: Invalid question_id {question_id} for this session in /update_mark_review_status") # DEBUG
        return jsonify(success=False, error="Invalid question ID for this session"), 400

    if 'marked_for_review' not in session:
        session['marked_for_review'] = {}

    if is_marked:
        session['marked_for_review'][question_id] = True
    else:
        session['marked_for_review'].pop(question_id, None)
    
    session.modified = True
    print(f"DEBUG: Mark for review status updated for {question_id}: {is_marked}") # DEBUG
    return jsonify(success=True, message="Mark for review status updated.")

@app.route('/test/question/<int:q_idx>', methods=['GET', 'POST'])
@login_required
def test_question_page(q_idx):
    print(f"\n--- test_question_page CALLED for q_idx: {q_idx}, Method: {request.method} ---")

    if 'test_questions_ids_ordered' not in session or not session['test_questions_ids_ordered']:
        flash('Test session not found or expired. Please start a new test.', 'warning')
        print("DEBUG: Test session or ordered_ids not found/empty at top of test_question_page.")
        return redirect(url_for('index'))
    
    ordered_ids = session['test_questions_ids_ordered']
    
    if not 0 <= q_idx < len(ordered_ids):
        current_q_idx_in_session = session.get('current_question_index', 0)
        print(f"DEBUG: Invalid q_idx {q_idx}. current_q_idx_in_session: {current_q_idx_in_session}, len(ordered_ids): {len(ordered_ids)}")
        if not (0 <= current_q_idx_in_session < len(ordered_ids)): # Validate session index too
            current_q_idx_in_session = 0 
        flash('Invalid question number accessed.', 'danger')
        return redirect(url_for('test_question_page', q_idx=current_q_idx_in_session))
    
    session['current_question_index'] = q_idx # Update current index in session
    question_id = ordered_ids[q_idx]
    question = ALL_QUESTIONS_MAP.get(question_id)
    
    if not question:
        flash('Error: Question data not found for the current question ID.', 'danger')
        print(f"DEBUG: Question data not found for q_id: {question_id} (index {q_idx}).")
        return redirect(url_for('test_question_page', q_idx=0)) # Default to first question

    if request.method == 'POST':
        print(f"--- POST request for q_idx: {q_idx} ---")
        print(f"Request form data: {request.form}")
        
        selected_option = request.form.get('answer')
        action = request.form.get('action')
        
        print(f"Selected answer from form: {selected_option}")
        print(f"Action from form: {action}")

        if selected_option: 
            session.setdefault('answers', {})[question_id] = selected_option
            print(f"Saved answer for {question_id}: {selected_option}")
        
        # 'mark_review' is handled by AJAX, so we don't need to process it from form submission here
        # unless as a fallback (but the checkbox name was changed to 'mark_review_visual_only')
        
        session.modified = True 
        
        if action == 'next':
            print(f"Action is 'next'. Current q_idx: {q_idx}, Total questions (len(ordered_ids)): {len(ordered_ids)}")
            next_q_idx = q_idx + 1
            if next_q_idx < len(ordered_ids): 
                print(f"Redirecting to next question: q_idx {next_q_idx}")
                return redirect(url_for('test_question_page', q_idx=next_q_idx))
            else: 
                print("This is the last question. Redirecting to results.")
                return redirect(url_for('results'))
        elif action == 'back':
            print(f"Action is 'back'. Current q_idx: {q_idx}")
            prev_q_idx = q_idx - 1
            if prev_q_idx >= 0: 
                print(f"Redirecting to previous question: q_idx {prev_q_idx}")
                return redirect(url_for('test_question_page', q_idx=prev_q_idx))
            else: # Should be disabled in frontend, but good to handle
                print("At first question, 'back' action received, redirecting to current q_idx.")
                return redirect(url_for('test_question_page', q_idx=q_idx)) # Stay on current page
        
        # Fallback if action is not 'next' or 'back' (e.g. None)
        print(f"Fallback: Action is '{action}'. Redirecting to current q_idx: {q_idx}")
        return redirect(url_for('test_question_page', q_idx=q_idx))

    # --- GET Request Logic ---
    print(f"--- GET request for q_idx: {q_idx} ---")
    current_section_name = "Math" if any(question_id == m_q['id'] for m_q in QUESTIONS_DATA.get('math', [])) else "Reading & Writing"
    current_module = question.get('module', 1)
    
    is_marked = session.get('marked_for_review', {}).get(question_id, False)
    selected_answer = session.get('answers', {}).get(question_id)
    print(f"Rendering template for q_idx: {q_idx}, question_id: {question_id}")
    print(f"Is marked for review: {is_marked}, Selected answer: {selected_answer}")
    
    return render_template('test_page.html', 
                           question=question, 
                           question_number=q_idx + 1, 
                           total_questions=TOTAL_QUESTIONS,
                           current_section=f"Section {1 if current_section_name == 'Math' else 2}, Module {current_module}: {current_section_name}",
                           start_time_iso=session.get('start_time', datetime.datetime.now().isoformat()),
                           test_duration_minutes=TEST_DURATION_MINUTES,
                           now=datetime.datetime.utcnow(), 
                           is_marked_for_review=is_marked,
                           selected_answer=selected_answer, 
                           q_idx=q_idx)

@app.route('/results')
@login_required
def results():
    if 'answers' not in session or 'start_time' not in session:
        flash('No answers recorded or session expired. Please start a new test.', 'warning')
        return redirect(url_for('index'))
    user_submitted_answers = session.get('answers', {})
    start_time_iso = session.get('start_time')
    if not start_time_iso: start_time = datetime.datetime.now() 
    else:
        try: start_time = datetime.datetime.fromisoformat(start_time_iso)
        except ValueError: start_time = datetime.datetime.now() 
    end_time = datetime.datetime.now(); time_taken_seconds = (end_time - start_time).total_seconds()
    results_summary = calculate_mock_score(user_submitted_answers)
    results_summary['time_taken_formatted'] = f"{int(time_taken_seconds // 60)}m {int(time_taken_seconds % 60)}s"
    answers_json_string = json.dumps(user_submitted_answers)
    new_score = Score(user_id=current_user.id, total_score=results_summary['total_score'], math_score=results_summary['math_score'], rw_score=results_summary['rw_score'], correct_count=results_summary['correct_count'], total_answered=results_summary['total_answered'], answers_data=answers_json_string, timestamp=end_time) 
    db.session.add(new_score); db.session.commit()
    for key in ['current_question_index', 'answers', 'start_time', 'test_questions_ids_ordered', 'marked_for_review']: session.pop(key, None)
    flash('Your test results have been saved!', 'success')
    return render_template('results_page.html', results=results_summary, score_id=new_score.id, now=datetime.datetime.utcnow())

@app.route('/download_report/<int:score_id>/<string:report_format>')
@login_required
def download_report(score_id, report_format):
    score_to_download = Score.query.filter_by(id=score_id, user_id=current_user.id).first_or_404()
    if report_format == 'csv':
        csv_data = generate_csv_report(score_to_download)
        return Response(csv_data, mimetype="text/csv", headers={"Content-disposition": f"attachment; filename=sat_detailed_report_{score_id}.csv"})
    flash("Invalid report format.", "danger"); return redirect(request.referrer or url_for('dashboard'))

@app.route('/reset_test', methods=['POST'])
@login_required
def reset_test():
    for key in ['current_question_index', 'answers', 'start_time', 'test_questions_ids_ordered', 'marked_for_review']: session.pop(key, None)
    flash('Test session reset. You can start a new test.', 'info'); return redirect(url_for('index'))

@app.errorhandler(404)
def page_not_found(e): return render_template('error_page.html', error_code=404, error_name="Page Not Found"), 404
@app.errorhandler(500)
def internal_server_error(e): return render_template('error_page.html', error_code=500, error_name="Internal Server Error"), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
