from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, jsonify
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
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///sattest.db'
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

# --- QUESTION DATA (from SAT Practice Test #6) ---
QUESTIONS_DATA = {
    "reading_writing": [
        {
            "id": "rw1", "module": 1, "passage": None,
            "text": "Though not closely related, the hedgehog tenrecs of Madagascar share basic ______ true hedgehogs, including protective spines, pointed snouts, and small body size-traits the two groups of mammals independently developed in response to equivalent roles in their respective habitats.",
            "options": ["examples of", "concerns about", "indications of", "similarities with"],
            "correctAnswer": "similarities with", "topic": "Words in Context", "difficulty": "Easy"
        },
        {
            "id": "rw2", "module": 1,
            "passage": "The following text is adapted from James Baldwin's 1956 novel Giovanni's Room. The narrator is riding in a taxi down a street lined with food vendors and shoppers in Paris, France.\n'The multitude of Paris seems to be dressed in blue every day but Sunday, when, for the most part, they put on an unbelievably festive black. Here they were now, in blue, disputing, every inch, our passage, with their wagons, handtrucks, their bursting baskets carried at an angle steeply self-confident on the back.'",
            "text": "As used in the text, what does the word \"disputing\" most nearly mean?",
            "options": ["Arguing about", "Disapproving of", "Asserting possession of", "Providing resistance to"],
            "correctAnswer": "Providing resistance to", "topic": "Words in Context", "difficulty": "Medium"
        },
        {
            "id": "rw3", "module": 1,
            "passage": "When classical pianist Martha Argerich performs, it appears as if the music is coming to her spontaneously. She's highly skilled technically, but because of how freely she plays and her willingness to take risks, she seems relaxed and natural. Her apparent ease, however, is due to a tremendous amount of preparation. Despite Argerich's experience and virtuosity, she never takes for granted that she knows a piece of music. Instead, she approaches the music as if encountering it for the first time and tries to understand it anew.",
            "text": "Which choice best states the main purpose of the text?",
            "options": ["To provide details about how Argerich identifies which pieces of music she will perform", "To assert that Argerich's performances look effortless because of how she prepares for them", "To discuss the kinds of music Argerich feels most comfortable encountering for the first time", "To describe the unique way that Argerich approaches music she hasn't performed before"],
            "correctAnswer": "To assert that Argerich's performances look effortless because of how she prepares for them", "topic": "Main Purpose", "difficulty": "Medium"
        },
        {
            "id": "rw4", "module": 1,
            "passage": "Text 1\nIn 1954 George Balanchine choreographed a production of The Nutcracker... But the show is stuck in the past, with an old-fashioned story and references, so it should no longer be produced. Ballet needs to create new traditions if it wants to stay relevant to contemporary audiences.\nText 2\nThe Nutcracker is outdated, but it should be kept because it's a holiday favorite and provides substantial income... Although it can be behind the times, there are creative ways to update the show... Her show Hot Chocolate Nutcracker combines ballet, tap, hip-hop, and other styles...",
            "text": "Based on the texts, how would the author of Text 2 most likely respond to the underlined claim in Text 1?",
            "options": ["By questioning the idea that the story of The Nutcracker is stuck in the past...", "By agreeing that contemporary audiences have largely stopped going...", "By pointing out that most dance companies could increase their incomes...", "By suggesting that dance companies should consider offering revised versions of The Nutcracker instead of completely rejecting the show"],
            "correctAnswer": "By suggesting that dance companies should consider offering revised versions of The Nutcracker instead of completely rejecting the show", "topic": "Comparing Texts", "difficulty": "Medium"
        },
        {
            "id": "rw5", "module": 1,
            "passage": "| Year | Number of cars produced | Number of companies producing cars |\n| :--- | :--- | :--- |\n| 1910 | 123,990 | 320 |\n| 1915 | 548,139 | 224 |\n| 1920 | 1,651,625 | 197 |\n| 1925 | 3,185,881 | 80 |",
            "text": "The student notes that, according to the table, from 1910 to 1925 ______",
            "options": ["the number of cars produced increased but the number of companies producing cars decreased.", "both the number of cars produced and the number of companies producing cars remained unchanged.", "the number of cars produced decreased but the number of companies producing cars remained unchanged.", "both the number of cars produced and the number of companies producing cars increased."],
            "correctAnswer": "the number of cars produced increased but the number of companies producing cars decreased.", "topic": "Data Interpretation", "difficulty": "Easy"
        },
        {
            "id": "rw6", "module": 1,
            "passage": "External shopping cues are a type of marketing that uses obvious messaging... The researchers explain that trying to find items in new locations causes shoppers to move through more of the store, exposing them to more products and increasing the likelihood that they'll buy an item they hadn't planned on purchasing.",
            "text": "Which response from a survey given to shoppers who made a purchase at a retail store best supports the researchers' explanation?",
            "options": ["\"I needed to buy some cleaning supplies, but they weren't in their regular place. While I was looking for them, I saw this interesting notebook and decided to buy it, too.\"", "\"I didn't buy everything on my shopping list today. I couldn't find a couple of the items in the store, even though I looked all over for them.\"", "\"The store sent me a coupon for a new brand of soup, so I came here to find out what kinds of soup that brand offers. I decided to buy a few cans because I had the coupon.\"", "\"This store is larger than one that's closer to where I live, and it carries more products. I came here to buy some things that the other store doesn't always have.\""],
            "correctAnswer": "\"I needed to buy some cleaning supplies, but they weren't in their regular place. While I was looking for them, I saw this interesting notebook and decided to buy it, too.\"", "topic": "Supporting Claims", "difficulty": "Medium"
        },
        {
            "id": "rw7", "module": 1,
            "passage": "To investigate potential cognitive benefits of taking leave from work...researchers concluded that longer leave times might not confer a greater cognitive benefit than shorter leave times do. [A bar chart shows that for the second and third tests, the '2-4 days leave' group had higher attentiveness scores than the '1-5 weeks leave' group.]",
            "text": "Which choice best describes data from the graph that support the researchers' conclusion?",
            "options": ["...participants who took 2-4 days of leave had higher average attentiveness scores than did those who took no leave...", "...participants who took 2-4 days of leave had lower average attentiveness scores than...", "In both the second and third test administrations, participants who took 2-4 days of leave had higher average attentiveness scores than did participants who took 1-5 weeks of leave.", "...participants who took 2-4 days of leave had higher average attentiveness scores than did those who took no leave."],
            "correctAnswer": "In both the second and third test administrations, participants who took 2-4 days of leave had higher average attentiveness scores than did participants who took 1-5 weeks of leave.", "topic": "Data Interpretation", "difficulty": "Hard"
        },
        {
            "id": "rw8", "module": 1, "passage": None,
            "text": "______ by businessman William A.G. Brown, the saloon was known to offer elegant accommodations and an inclusive environment.",
            "options": ["Created", "Creates", "Creating", "Create"],
            "correctAnswer": "Created", "topic": "Grammar", "difficulty": "Easy"
        },
        {
            "id": "rw9", "module": 1, "passage": None,
            "text": "It's an example of antimetabole, a writing technique that ______ emphasis by repeating a statement in a reversed order.",
            "options": ["create", "are creating", "have created", "creates"],
            "correctAnswer": "creates", "topic": "Grammar", "difficulty": "Easy"
        },
        {
            "id": "rw10", "module": 1, "passage": None,
            "text": "A ray diagram reveals how this ______ the hole's small size restricts light to a single ray, all light passing through the hole can only arrive at a single destination, eliminating diffraction and ensuring a clear image.",
            "options": ["works because", "works. Because", "works, it's because", "works: it's because"],
            "correctAnswer": "works because", "topic": "Punctuation", "difficulty": "Medium"
        },
        {
            "id": "rw11", "module": 1, "passage": None,
            "text": "Before it unveiled a massive new gallery in 2009, the Art Institute of Chicago was only able to display about 5% of its art collection. ______ the museum is able to display close to 30% of its collection.",
            "options": ["Additionally,", "For example,", "Nevertheless,", "Today,"],
            "correctAnswer": "Today,", "topic": "Logical Transitions", "difficulty": "Easy"
        },
        {
            "id": "rw12", "module": 1,
            "passage": "Notes:\n- In the 1930s, the Imperial Sugar Cane Institute in India sought to limit the country's dependence on imported sugarcane.\n- The institute enlisted botanist Janaki Ammal to breed a local variety of sugarcane.\n- She crossbred the imported sugarcane species Saccharum officinarum with grasses native to India.\n- She succeeded in creating sugarcane hybrids well suited to India's climate.",
            "text": "The student wants to emphasize Janaki Ammal's achievement. Which choice most effectively uses relevant information from the notes to accomplish this goal?",
            "options": ["By crossbreeding the imported sugarcane species Saccharum officinarum with grasses native to India, Ammal succeeded in creating sugarcane hybrids well suited to India's climate.", "In the 1930s, the Imperial Sugar Cane Institute, which enlisted Ammal, sought to limit dependence on imported sugarcane.", "Ammal was enlisted by the Imperial Sugar Cane Institute at a time when a local variety of sugarcane needed to be produced.", "As part of efforts to breed a local variety of sugarcane, an imported sugarcane species called Saccharum officinarum was crossbred with grasses native to India."],
            "correctAnswer": "By crossbreeding the imported sugarcane species Saccharum officinarum with grasses native to India, Ammal succeeded in creating sugarcane hybrids well suited to India's climate.", "topic": "Rhetorical Synthesis", "difficulty": "Medium"
        }
    ],
    "math": [
        {
            "id": "m1", "module": 1, "passage": None,
            "text": "(p + 3) + 8 = 10\nWhat value of p is the solution to the given equation?",
            "options": ["-1", "5", "15", "21"], "correctAnswer": "-1", "topic": "Algebra", "difficulty": "Easy"
        },
        {
            "id": "m2", "module": 1, "passage": None,
            "text": "An object was launched upward from a platform. The graph shown models the height above ground, y, in meters, of the object x seconds after it was launched. [A parabola opening downwards, starting at (0, 10), reaching a vertex near (2.5, 28), and hitting the x-axis around 4.5.]\n\nFor which of the following intervals of time was the height of the object increasing for the entire interval?",
            "options": ["From x=0 to x=2", "From x=0 to x=4", "From x=2 to x=3", "From x=3 to x=4"],
            "correctAnswer": "From x=0 to x=2", "topic": "Data Interpretation", "difficulty": "Easy"
        },
        {
            "id": "m3", "module": 1, "passage": None,
            "text": "How many yards are equivalent to 1,116 inches? (1 yard = 36 inches)",
            "options": [], "correctAnswer": "31", "topic": "Problem Solving", "difficulty": "Easy"
        },
        {
            "id": "m4", "module": 1, "passage": None,
            "text": "P(t) = 1,800(1.02)ᵗ\nThe function P gives the estimated number of marine mammals in a certain area, where t is the number of years since a study began. What is the best interpretation of P(0) = 1,800 in this context?",
            "options": ["The estimated number of marine mammals in the area was 102 when the study began.", "The estimated number of marine mammals in the area was 1,800 when the study began.", "The estimated number of marine mammals in the area increased by 102 each year during the study.", "The estimated number of marine mammals in the area increased by 1,800 each year during the study."],
            "correctAnswer": "The estimated number of marine mammals in the area was 1,800 when the study began.", "topic": "Algebra", "difficulty": "Easy"
        },
        {
            "id": "m5", "module": 1, "passage": None,
            "text": "The figure shows the lengths, in inches, of two sides of a right triangle. [A right triangle with legs of length 3 and 5.]\n\nWhat is the area of the triangle, in square inches?",
            "options": [], "correctAnswer": "7.5", "topic": "Geometry", "difficulty": "Easy"
        },
        {
            "id": "m6", "module": 1, "passage": None,
            "text": "The relationship between two variables, x and y, is linear. For every increase in the value of x by 1, the value of y increases by 8. When the value of x is 2, the value of y is 18.\n\nWhich equation represents this relationship?",
            "options": ["y = 2x + 18", "y = 2x + 8", "y = 8x + 2", "y = 8x + 26"],
            "correctAnswer": "y = 8x + 2", "topic": "Algebra", "difficulty": "Medium"
        },
        {
            "id": "m7", "module": 1, "passage": None,
            "text": "w² + 12w - 40 = 0\nWhich of the following is a solution to the given equation?",
            "options": ["6 - 2√19", "2√19", "√19", "-6 + 2√19"],
            "correctAnswer": "-6 + 2√19", "topic": "Advanced Math", "difficulty": "Hard"
        },
        {
            "id": "m8", "module": 1, "passage": None,
            "text": "The graph of y = 2x² + bx + c is shown, where b and c are constants. [A parabola opening upwards with its vertex at (-1, -8) and a y-intercept at (0, -6).]\n\nWhat is the value of bc?",
            "options": [], "correctAnswer": "-24", "topic": "Advanced Math", "difficulty": "Hard"
        },
        {
            "id": "m9", "module": 1, "passage": None,
            "text": "Right triangle ABC is shown. Angle C is the right angle. [A right triangle ABC, with the right angle at C. The hypotenuse AB has length 54, and angle B is 30°.]\n\nWhat is the value of tan A?",
            "options": ["√3/54", "1/√3", "√3", "27√3"],
            "correctAnswer": "√3", "topic": "Trigonometry", "difficulty": "Medium"
        },
        {
            "id": "m10", "module": 1, "passage": None,
            "text": "A rectangle has an area of 155 square inches. The length of the rectangle is 4 inches less than 7 times the width of the rectangle.\n\nWhat is the width of the rectangle, in inches?",
            "options": [], "correctAnswer": "5", "topic": "Algebra", "difficulty": "Medium"
        }
    ]
}

ALL_QUESTIONS = QUESTIONS_DATA["reading_writing"] + QUESTIONS_DATA["math"]
ALL_QUESTIONS_MAP = {q['id']: q for q in ALL_QUESTIONS}
ORDERED_QUESTION_IDS = [q['id'] for q in ALL_QUESTIONS]

TOTAL_QUESTIONS = len(ALL_QUESTIONS)
TEST_DURATION_MINUTES = 30

def initialize_test_session():
    session['current_question_index'] = 0
    session['answers'] = {}
    session['start_time'] = datetime.datetime.utcnow().isoformat() + "Z"
    session['test_questions_ids_ordered'] = ORDERED_QUESTION_IDS[:]
    session['marked_for_review'] = {}

def calculate_mock_score(answers):
    correct_count = 0; math_correct = 0; math_total = 0; rw_correct = 0; rw_total = 0
    for q_id, user_answer in answers.items():
        question_detail = ALL_QUESTIONS_MAP.get(q_id)
        if not question_detail: continue
        is_math = q_id.startswith('m')
        if is_math: math_total += 1
        else: rw_total += 1
        if user_answer == question_detail['correctAnswer']:
            correct_count += 1
            if is_math: math_correct += 1
            else: rw_correct += 1
    math_score_ratio = (math_correct / max(1, math_total)) if math_total > 0 else 0
    rw_score_ratio = (rw_correct / max(1, rw_total)) if rw_total > 0 else 0
    mock_math_score = max(200, min(800, 200 + int(math_score_ratio * 600)))
    mock_rw_score = max(200, min(800, 200 + int(rw_score_ratio * 600)))
    mock_total_score = max(400, min(1600, mock_math_score + mock_rw_score))
    weaknesses = []; recommendations = []
    if math_total > 0 and math_score_ratio < 0.6: weaknesses.append("Algebra Concepts (Math)"); recommendations.append("Review foundational algebra topics.")
    if rw_total > 0 and rw_score_ratio < 0.6: weaknesses.append("Grammar Rules (Reading & Writing)"); recommendations.append("Focus on Standard English Conventions.")
    if not weaknesses and (math_total > 0 or rw_total > 0): recommendations.append("Continue practicing across all topics.")
    elif not weaknesses and math_total == 0 and rw_total == 0: weaknesses.append("No answers to analyze."); recommendations.append("Complete the test for analysis.")
    return {"total_score": mock_total_score, "math_score": mock_math_score, "rw_score": mock_rw_score, "correct_count": correct_count, "total_answered": len(answers), "weaknesses": weaknesses, "recommendations": recommendations}

def generate_csv_report(score_obj):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Question Number", "Section", "Skill Type", "Your Answer", "Correct Answer", "Outcome"])
    if not score_obj or not score_obj.answers_data:
        writer.writerow(["N/A"] * 6)
        output.seek(0)
        return output.getvalue()
    try:
        user_answers_dict = json.loads(score_obj.answers_data)
    except json.JSONDecodeError:
        writer.writerow(["Error decoding answers"] + ["N/A"] * 5)
        output.seek(0)
        return output.getvalue()
    question_sequence_number = 0
    for q_id in ORDERED_QUESTION_IDS:
        question_sequence_number += 1
        question_detail = ALL_QUESTIONS_MAP.get(q_id)
        if not question_detail:
            writer.writerow([question_sequence_number, "Unknown", "Unknown", "N/A", "N/A", "Question detail missing"])
            continue
        section_val = "Math" if q_id.startswith('m') else "Reading & Writing"
        skill_type_val = question_detail.get("topic", "N/A")
        user_answer_val = user_answers_dict.get(q_id, "Not Answered")
        correct_answer_val = question_detail.get("correctAnswer", "N/A")
        outcome_val = "Incorrect"
        if user_answer_val == correct_answer_val:
            outcome_val = "Correct"
        elif user_answer_val == "Not Answered":
            outcome_val = "Not Answered"
        writer.writerow([question_sequence_number, section_val, skill_type_val, user_answer_val, correct_answer_val, outcome_val])
    output.seek(0)
    return output.getvalue()

# --- Routes ---
@app.route('/')
def index(): return render_template('index.html', total_questions=TOTAL_QUESTIONS, duration=TEST_DURATION_MINUTES, now=datetime.datetime.utcnow())

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username'); password = request.form.get('password')
        if not username or not password: flash('Username and password are required.', 'warning'); return redirect(url_for('register'))
        if User.query.filter_by(username=username).first(): flash('Username already exists.', 'danger'); return redirect(url_for('register'))
        new_user = User(username=username); new_user.set_password(password); db.session.add(new_user); db.session.commit(); flash('Registration successful! Please log in.', 'success'); return redirect(url_for('login'))
    return render_template('register.html', now=datetime.datetime.utcnow())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username'); password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password): login_user(user, remember=request.form.get('remember') == 'on'); flash('Logged in successfully!', 'success'); return redirect(request.args.get('next') or url_for('index'))
        else: flash('Invalid username or password.', 'danger')
    return render_template('login.html', now=datetime.datetime.utcnow())

@app.route('/logout')
@login_required
def logout(): logout_user(); flash('You have been logged out.', 'info'); return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard(): user_scores = Score.query.filter_by(user_id=current_user.id).order_by(Score.timestamp.desc()).all(); return render_template('dashboard.html', scores=user_scores, now=datetime.datetime.utcnow())

@app.route('/start_test', methods=['POST'])
@login_required
def start_test():
    initialize_test_session()
    return redirect(url_for('test_question_page', q_num=1))

@app.route('/update_mark_review_status', methods=['POST'])
@login_required
def update_mark_review_status():
    if 'test_questions_ids_ordered' not in session: return jsonify(success=False, error="Test session not found"), 400
    data = request.get_json()
    if not data: return jsonify(success=False, error="No data received"), 400
    question_id = data.get('question_id'); is_marked = data.get('mark_review')
    if question_id is None or not isinstance(is_marked, bool): return jsonify(success=False, error="Invalid data"), 400
    if question_id not in session.get('test_questions_ids_ordered', []): return jsonify(success=False, error="Invalid question ID"), 400
    session.setdefault('marked_for_review', {})
    if is_marked: session['marked_for_review'][question_id] = True
    else: session['marked_for_review'].pop(question_id, None)
    session.modified = True
    return jsonify(success=True)

@app.route('/test/question/<int:q_num>', methods=['GET', 'POST'])
@login_required
def test_question_page(q_num):
    if 'test_questions_ids_ordered' not in session or not session['test_questions_ids_ordered']:
        flash('Test session not found or expired. Please start a new test.', 'warning')
        return redirect(url_for('index'))
    ordered_ids = session['test_questions_ids_ordered']
    q_idx = q_num - 1
    if not 0 <= q_idx < len(ordered_ids):
        flash('Invalid question number.', 'danger')
        return redirect(url_for('test_question_page', q_num=1))
    session['current_question_index'] = q_idx
    question_id = ordered_ids[q_idx]
    question = ALL_QUESTIONS_MAP.get(question_id)
    if not question:
        flash('Error: Question data not found.', 'danger')
        return redirect(url_for('test_question_page', q_num=1))
    if request.method == 'POST':
        selected_option = request.form.get('answer'); action = request.form.get('action')
        if selected_option:
            session.setdefault('answers', {})[question_id] = selected_option
        session.modified = True
        if action == 'next':
            if q_num < len(ordered_ids):
                return redirect(url_for('test_question_page', q_num=q_num + 1))
            else:
                return redirect(url_for('results'))
        elif action == 'back':
            if q_num > 1:
                return redirect(url_for('test_question_page', q_num=q_num - 1))
        return redirect(url_for('test_question_page', q_num=q_num))
    current_section_name = "Math" if question_id.startswith('m') else "Reading & Writing"
    current_module = question.get('module', 1)
    is_marked = session.get('marked_for_review', {}).get(question_id, False)
    selected_answer = session.get('answers', {}).get(question_id)
    return render_template('test_page.html',
                           question=question,
                           question_number=q_num,
                           total_questions=TOTAL_QUESTIONS,
                           current_section=f"Section {1 if current_section_name == 'Math' else 2}, Module {current_module}: {current_section_name}",
                           start_time_iso=session.get('start_time', datetime.datetime.utcnow().isoformat() + "Z"),
                           test_duration_minutes=TEST_DURATION_MINUTES,
                           now=datetime.datetime.utcnow(),
                           is_marked_for_review=is_marked,
                           selected_answer=selected_answer,
                           q_idx=q_idx,
                           q_num=q_num)

@app.route('/results')
@login_required
def results():
    if 'answers' not in session or 'start_time' not in session:
        flash('No answers or session expired.', 'warning')
        return redirect(url_for('index'))
    user_answers = session.get('answers', {})
    start_time_iso = session.get('start_time')
    try:
        if start_time_iso and start_time_iso.endswith('Z'):
            start_time_iso = start_time_iso[:-1]
        start_time = datetime.datetime.fromisoformat(start_time_iso)
    except (ValueError, TypeError):
        start_time = datetime.datetime.utcnow()
    end_time = datetime.datetime.utcnow()
    time_taken = (end_time - start_time).total_seconds()
    summary = calculate_mock_score(user_answers)
    summary['time_taken_formatted'] = f"{int(time_taken // 60)}m {int(time_taken % 60)}s"
    answers_json = json.dumps(user_answers)
    score = Score(user_id=current_user.id,
                  total_score=summary['total_score'],
                  math_score=summary['math_score'],
                  rw_score=summary['rw_score'],
                  correct_count=summary['correct_count'],
                  total_answered=summary['total_answered'],
                  answers_data=answers_json,
                  timestamp=end_time)
    db.session.add(score)
    db.session.commit()
    for key in ['current_question_index', 'answers', 'start_time', 'test_questions_ids_ordered', 'marked_for_review']:
        session.pop(key, None)
    flash('Test results saved!', 'success')
    return render_template('results_page.html', results=summary, score_id=score.id, now=datetime.datetime.utcnow())

@app.route('/download_report/<int:score_id>/<string:report_format>')
@login_required
def download_report(score_id, report_format):
    score = Score.query.filter_by(id=score_id, user_id=current_user.id).first_or_404()
    if report_format == 'csv': return Response(generate_csv_report(score), mimetype="text/csv", headers={"Content-disposition": f"attachment; filename=report_{score_id}.csv"})
    flash("Invalid report format.", "danger"); return redirect(request.referrer or url_for('dashboard'))

@app.route('/reset_test', methods=['POST'])
@login_required
def reset_test():
    for key in ['current_question_index', 'answers', 'start_time', 'test_questions_ids_ordered', 'marked_for_review']: session.pop(key, None)
    flash('Test session reset.', 'info'); return redirect(url_for('index'))

@app.errorhandler(404)
def e404(e): return render_template('error_page.html', error_code=404, error_name="Page Not Found", error_message="Sorry, the page you are looking for does not exist."), 404
@app.errorhandler(500)
def e500(e): db.session.rollback(); return render_template('error_page.html', error_code=500, error_name="Internal Server Error", error_message="We are experiencing some technical difficulties. Please try again later."), 500

if __name__ == '__main__':
    with app.app_context(): db.create_all()
    app.run(debug=True)
