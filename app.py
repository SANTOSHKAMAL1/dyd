"""
Jain University Course & Career Advisor - Flask Application
"""

import os
import json
import uuid
from datetime import datetime
from functools import wraps
import pytz
import pandas as pd
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import plotly
import plotly.graph_objects as go
import base64
from io import BytesIO

# Import utility modules
from utils_def_1 import (
    driver, NEO4J_DATABASE, get_mistral_client, mistral_request, 
    MISTRAL_MODEL, MISTRAL_API_KEY, embedding_model, EMBED_DIM
)
from util_func_1 import (
    process_user_query, generate_response, SlidingWindowMemory,
    save_chat_message, load_chat_history, clear_chat_history,
    get_user_profile, save_user_profile, save_marks, get_user_marks,
    delete_mark, update_mark, update_marks_completed,
    get_user_riasec_results, save_riasec_results, calculate_riasec_scores,
    get_trait_name, get_riasec_trait_description
)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "jain-university-secret-key-2025")

# RIASEC Questions
RIASEC_QUESTIONS = [
    ("I like to work on cars", "R"),
    ("I like to build things", "R"),
    ("I like putting things together or assembling things.", "R"),
    ("I like to take care of animals", "R"),
    ("I like to cook", "R"),
    ("I am a practical person", "R"),
    ("I like working outdoors", "R"),
    ("I like working with numbers or charts", "I"),
    ("I'm good at math", "I"),
    ("I enjoy trying to figure out how things work", "I"),
    ("I like to analyze things (problems/situations)", "I"),
    ("I like to do puzzles", "I"),
    ("I enjoy science", "I"),
    ("I like to do experiments", "I"),
    ("I like to teach or train people", "S"),
    ("I like to play instruments or sing", "A"),
    ("I like to read about art and music", "A"),
    ("I like to draw", "A"),
    ("I enjoy creative writing", "A"),
    ("I am a creative person", "A"),
    ("I like acting in plays", "A"),
    ("I like helping people", "S"),
    ("I like to get into discussions about issues", "S"),
    ("I enjoy learning about other cultures", "S"),
    ("I am interested in healing people", "S"),
    ("I like trying to help people solve their problems", "S"),
    ("I like to work in teams", "S"),
    ("I am an ambitious person, I set goals for myself", "E"),
    ("I would like to start my own business", "E"),
    ("I am quick to take on new responsibilities", "E"),
    ("I like selling things", "E"),
    ("I like to lead", "E"),
    ("I like to try to influence or persuade people", "E"),
    ("I like to give speeches", "E"),
    ("I like to organize things, (files, desks/offices)", "C"),
    ("I like to have clear instructions to follow", "C"),
    ("I wouldn't mind working 8 hours per day in an office", "C"),
    ("I pay attention to details", "C"),
    ("I like to do filing or typing", "C"),
    ("I am good at keeping records of my work", "C"),
    ("I would like to work in an office", "C"),
]

DEFAULT_SUBJECTS = [
    "English", "Mathematics", "Language", "Science", "Physics",
    "Chemistry", "Biology", "Zoology", "Home Science",
    "History", "Geography", "Computer Science", "Economics",
    "Business Studies", "Accountancy", "Psychology", "Sociology"
]

# Helper Functions
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('home'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Username and password required!', 'error')
            return render_template('login.html')
        
        if not driver:
            flash('Database connection error!', 'error')
            return render_template('login.html')
        
        try:
            with driver.session(database=NEO4J_DATABASE) as s:
                result = s.run("""
                    MATCH (u:User {username:$username}) 
                    RETURN u.password AS password, 
                           u.marks_completed AS marks_completed,
                           u.riasec_completed AS riasec_completed
                """, username=username).single()

            if result and check_password_hash(result["password"], password):
                session['username'] = username
                session['logged_in'] = True
                
                # Redirect based on completion status - NEW USER FLOW
                marks_completed = result.get("marks_completed", False)
                riasec_completed = result.get("riasec_completed", False)
                
                if not marks_completed:
                    # New user - first go to marks entry
                    flash('Welcome! Please enter your academic marks to get started.', 'info')
                    return redirect(url_for('marks'))
                elif not riasec_completed:
                    # Marks completed but RIASEC not done
                    flash('Great! Now complete the career assessment to get personalized recommendations.', 'info')
                    return redirect(url_for('survey'))
                else:
                    # Both completed - go to home/dashboard
                    flash('Welcome back!', 'success')
                    return redirect(url_for('home'))
            else:
                flash('Invalid username or password!', 'error')
        except Exception as e:
            flash(f'Login error: {e}', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not username or not password:
            flash('Username and password required!', 'error')
            return render_template('register.html')
        
        if password != confirm_password:
            flash('Passwords do not match!', 'error')
            return render_template('register.html')
        
        if not driver:
            flash('Database connection error!', 'error')
            return render_template('register.html')
        
        hashed_password = generate_password_hash(password)
        
        try:
            with driver.session(database=NEO4J_DATABASE) as s:
                exists = s.run("MATCH (u:User {username:$username}) RETURN u", username=username).single()
                if exists:
                    flash('Username already exists!', 'error')
                    return render_template('register.html')
                
                # Create user with initial profile data
                s.run("""
                    CREATE (u:User {
                        username: $username, 
                        password: $password, 
                        email: $email,
                        display_name: $display_name,
                        created_at: datetime(),
                        marks_completed: false,
                        riasec_completed: false,
                        bio: 'New student at Jain University',
                        location: '',
                        phone: ''
                    })
                """, 
                username=username, 
                password=hashed_password, 
                email=email,
                display_name=username)
            
            flash('Registered successfully! Please login.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'Registration error: {e}', 'error')
    
    return render_template('register.html')

@app.route('/home')
@login_required
def home():
    profile = get_user_profile(session['username'])
    marks_data = get_user_marks(session['username'])
    riasec_data = get_user_riasec_results(session['username'])
    
    # Check if user has completed both steps
    marks_completed = profile and profile.get('marks_completed')
    riasec_completed = profile and profile.get('riasec_completed')
    
    stats = {
        'completion': 100 if (marks_completed and riasec_completed) else 50,
        'subjects_count': len(marks_data),
        'average_score': sum(m['percentage'] for m in marks_data) / len(marks_data) if marks_data else 0,
        'riasec_status': "Done" if riasec_completed else "Pending",
        'marks_status': "Done" if marks_completed else "Pending"
    }
    
    return render_template('home.html', 
                         username=session['username'],
                         stats=stats,
                         profile=profile,
                         riasec_data=riasec_data,
                         marks_completed=marks_completed,
                         riasec_completed=riasec_completed)

@app.route('/marks', methods=['GET', 'POST'])
@login_required
def marks():
    if request.method == 'POST':
        if 'add_marks' in request.form:
            subject = request.form.get('subject')
            marks_scored = float(request.form.get('marks_scored'))
            total_marks = float(request.form.get('total_marks'))
            
            if not subject:
                flash('Please select or enter a valid subject name!', 'error')
            elif marks_scored > total_marks:
                flash('Marks scored cannot exceed total marks!', 'error')
            else:
                result = save_marks(session['username'], subject, marks_scored, total_marks)
                if result == "exists":
                    flash(f'Marks for "{subject}" already exist! Please edit the existing entry.', 'warning')
                elif result:
                    flash(f'Marks added for {subject}!', 'success')
                else:
                    flash('Error saving marks!', 'error')
        
        elif 'finish' in request.form:
            marks_data = get_user_marks(session['username'])
            if len(marks_data) == 0:
                flash('Please add at least one subject\'s marks before continuing!', 'warning')
            else:
                update_marks_completed(session['username'])
                session['marks_completed'] = True
                flash('Great! Now let\'s complete the RIASEC assessment to discover your career interests.', 'success')
                return redirect(url_for('survey'))
        
        elif 'delete_mark' in request.form:
            mark_id = request.form.get('mark_id')
            if delete_mark(mark_id):
                flash('Mark deleted successfully!', 'success')
            else:
                flash('Error deleting mark!', 'error')
        
        elif 'update_mark' in request.form:
            mark_id = request.form.get('mark_id')
            marks_scored = float(request.form.get('marks_scored'))
            total_marks = float(request.form.get('total_marks'))
            
            if marks_scored > total_marks:
                flash('Marks cannot exceed total!', 'error')
            else:
                if update_mark(mark_id, marks_scored, total_marks):
                    flash('Mark updated successfully!', 'success')
                else:
                    flash('Error updating mark!', 'error')
    
    marks_data = get_user_marks(session['username'])
    
    # Get completion status to show appropriate messaging
    profile = get_user_profile(session['username'])
    marks_completed = profile and profile.get('marks_completed')
    
    return render_template('marks.html', 
                         marks_data=marks_data,
                         default_subjects=DEFAULT_SUBJECTS,
                         username=session['username'],
                         marks_completed=marks_completed)

@app.route('/survey', methods=['GET', 'POST'])
@login_required
def survey():
    if request.method == 'POST':
        try:
            print("=== SURVEY SUBMISSION STARTED ===")
            data = request.get_json()
            print(f"Received data type: {type(data)}")
            print(f"Received data: {data}")
            
            answers = data.get('answers', {})
            print(f"Answers count: {len(answers)}")
            print(f"Sample answers: {dict(list(answers.items())[:3])}")  # First 3 answers
            
            # Check if answers are valid
            valid_answers = {k: v for k, v in answers.items() if v in [0, 1]}
            print(f"Valid answers count: {len(valid_answers)}")
            
            if len(valid_answers) != 42:
                print(f"WARNING: Expected 42 answers, got {len(valid_answers)} valid answers")
            
            # Calculate RIASEC results
            print("Calculating RIASEC scores...")
            riasec_results = calculate_riasec_scores(answers)
            print(f"RIASEC results calculated: {riasec_results}")
            
            # Save to database
            print("Saving to database...")
            username = session['username']
            print(f"Saving for user: {username}")
            
            success = save_riasec_results(username, answers, riasec_results)
            print(f"Save result: {success}")
            
            if success:
                print("Successfully saved results")
                return jsonify({'success': True})
            else:
                print("Failed to save results")
                return jsonify({'success': False, 'message': 'Error saving results to database'}), 500
                
        except Exception as e:
            print(f"=== ERROR PROCESSING SURVEY ===")
            print(f"Error type: {type(e)}")
            print(f"Error message: {str(e)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500
    
    # GET request - show survey form
    riasec_data = get_user_riasec_results(session['username'])
    
    if riasec_data:
        flash('You can review your previous results or retake the assessment.', 'info')
    
    return render_template('survey.html', 
                         username=session['username'],
                         riasec_data=riasec_data,
                         get_trait_name=get_trait_name)

@app.route('/dashboard')
@login_required
def dashboard():
    if not driver:
        flash('Database connection error!', 'error')
        return redirect(url_for('home'))
    
    # Check if user has completed both steps
    profile = get_user_profile(session['username'])
    if not profile or not profile.get('marks_completed'):
        flash('Please complete your marks entry first!', 'warning')
        return redirect(url_for('marks'))
    
    if not profile.get('riasec_completed'):
        flash('Please complete the RIASEC assessment first!', 'warning')
        return redirect(url_for('survey'))
    
    # Get RIASEC results from database
    riasec_data = get_user_riasec_results(session['username'])
    
    if not riasec_data:
        flash('Please complete the RIASEC assessment first.', 'warning')
        return redirect(url_for('survey'))

    scores = riasec_data['scores']
    top3 = riasec_data['top3']
    timestamp = riasec_data['timestamp']

    # Create radar chart
    labels = ['Realistic', 'Investigative', 'Artistic', 'Social', 'Enterprising', 'Conventional']
    values = [
        round(scores.get('R', 0) * 100, 1),
        round(scores.get('I', 0) * 100, 1),
        round(scores.get('A', 0) * 100, 1),
        round(scores.get('S', 0) * 100, 1),
        round(scores.get('E', 0) * 100, 1),
        round(scores.get('C', 0) * 100, 1)
    ]

    fig = go.Figure(data=go.Scatterpolar(
        r=values,
        theta=labels,
        fill='toself',
        fillcolor='rgba(52, 152, 219, 0.3)',
        line=dict(color='rgb(52, 152, 219)'),
        marker=dict(color='rgb(52, 152, 219)')
    ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                tickfont=dict(size=10)
            ),
            angularaxis=dict(
                tickfont=dict(size=11)
            )
        ),
        showlegend=False,
        height=400,
        margin=dict(l=50, r=50, t=50, b=50)
    )

    chart_json = plotly.io.to_json(fig)

    marks_data = get_user_marks(session['username'])
    
    return render_template('dashboard.html',
                         username=session['username'],
                         scores=scores,
                         top3=top3, 
                         timestamp=timestamp,
                         chart_json=chart_json,
                         marks_data=marks_data,
                         get_trait_name=get_trait_name,
                         get_riasec_trait_description=get_riasec_trait_description,
                         riasec_data=riasec_data)

@app.route('/assistant')
@login_required
def assistant():
    # Check if user has completed both steps
    profile = get_user_profile(session['username'])
    if not profile or not profile.get('marks_completed'):
        flash('Please complete your marks entry first to get personalized recommendations!', 'warning')
        return redirect(url_for('marks'))
    
    if not profile.get('riasec_completed'):
        flash('Please complete the RIASEC assessment to get career-specific advice!', 'warning')
        return redirect(url_for('survey'))
    
    chat_messages = load_chat_history(session['username'])
    return render_template('assistant.html',
                         username=session['username'],
                         chat_messages=chat_messages,
                         driver_connected=bool(driver),
                         mistral_available=bool(MISTRAL_API_KEY and get_mistral_client(MISTRAL_API_KEY)))

@app.route('/chat/send', methods=['POST'])
@login_required
def send_chat():
    user_input = request.json.get('message')
    if not user_input:
        return jsonify({'error': 'No message provided'}), 400
    
    # Save user message to Neo4j
    save_chat_message(session['username'], "user", user_input)
    
    # Process query
    query_results = process_user_query(driver, user_input)
    
    # Get response
    client = get_mistral_client(MISTRAL_API_KEY) if MISTRAL_API_KEY else None
    chat_history = load_chat_history(session['username'])
    
    assistant_response = generate_response(
        query_results=query_results,
        user_input=user_input,
        client=client,
        conversation_history=chat_history,
        _drv=driver,
        database_name=NEO4J_DATABASE,
        username=session['username']
    )
    
    # Save assistant response to Neo4j
    save_chat_message(session['username'], "assistant", assistant_response)
    
    response_data = {
        'response': assistant_response,
        'courses_count': len(query_results.get('courses', [])),
        'jobs_count': len(query_results.get('jobs', []))
    }
    
    return jsonify(response_data)

@app.route('/chat/clear', methods=['POST'])
@login_required
def clear_chat():
    clear_chat_history(session['username'])
    return jsonify({'success': True})

@app.route('/profile')
@login_required
def profile():
    user_profile = get_user_profile(session['username'])
    marks_data = get_user_marks(session['username'])
    riasec_data = get_user_riasec_results(session['username'])
    
    return render_template('profile.html',
                         username=session['username'],
                         profile=user_profile,
                         marks_data=marks_data,
                         riasec_data=riasec_data,
                         get_trait_name=get_trait_name,
                         get_riasec_trait_description=get_riasec_trait_description)

@app.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    display_name = request.form.get('display_name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    location = request.form.get('location')
    bio = request.form.get('bio')
    
    success = True
    if display_name:
        success = success and save_user_profile(session['username'], 'display_name', display_name)
    if email:
        success = success and save_user_profile(session['username'], 'email', email)
    if phone:
        success = success and save_user_profile(session['username'], 'phone', phone)
    if location:
        success = success and save_user_profile(session['username'], 'location', location)
    if bio:
        success = success and save_user_profile(session['username'], 'bio', bio)
    
    if success:
        flash('Profile updated successfully!', 'success')
    else:
        flash('Error updating profile!', 'error')
    
    return redirect(url_for('profile'))

# Route to upload profile/cover images
@app.route('/profile/upload-image', methods=['POST'])
@login_required
def upload_profile_image():
    try:
        data = request.json
        image_type = data.get('type')  # 'profile' or 'cover'
        image_data = data.get('image')
        
        if not image_data or not image_type:
            return jsonify({'success': False, 'message': 'Missing data'}), 400
        
        # Save to Neo4j
        if not driver:
            return jsonify({'success': False, 'message': 'Database error'}), 500
        
        with driver.session(database=NEO4J_DATABASE) as s:
            if image_type == 'profile':
                s.run("""
                    MATCH (u:User {username: $username})
                    SET u.profile_image = $image
                """, username=session['username'], image=image_data)
            elif image_type == 'cover':
                s.run("""
                    MATCH (u:User {username: $username})
                    SET u.cover_image = $image
                """, username=session['username'], image=image_data)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# Route to get profile/cover images
@app.route('/profile/get-images')
@login_required
def get_profile_images():
    try:
        if not driver:
            return jsonify({'profile_image': None, 'cover_image': None})
        
        with driver.session(database=NEO4J_DATABASE) as s:
            result = s.run("""
                MATCH (u:User {username: $username})
                RETURN u.profile_image AS profile_image, 
                       u.cover_image AS cover_image
            """, username=session['username']).single()
        
        if result:
            return jsonify({
                'profile_image': result.get('profile_image'),
                'cover_image': result.get('cover_image')
            })
        
        return jsonify({'profile_image': None, 'cover_image': None})
    except Exception as e:
        return jsonify({'profile_image': None, 'cover_image': None})

# Public profile view (no login required)
@app.route('/public-profile/<username>')
def public_profile(username):
    """Public profile page that anyone can view without login"""
    try:
        if not driver:
            flash('Database connection error!', 'error')
            return redirect(url_for('login'))
        
        # Get user profile data
        with driver.session(database=NEO4J_DATABASE) as s:
            result = s.run("""
                MATCH (u:User {username: $username})
                RETURN u.username AS username,
                       u.display_name AS display_name,
                       u.email AS email,
                       u.phone AS phone,
                       u.location AS location,
                       u.bio AS bio,
                       u.profile_image AS profile_image,
                       u.cover_image AS cover_image,
                       u.marks_completed AS marks_completed,
                       u.riasec_completed AS riasec_completed
            """, username=username).single()
        
        if not result:
            flash('Profile not found!', 'error')
            return redirect(url_for('login'))
        
        profile = {
            'username': result.get('username'),
            'display_name': result.get('display_name'),
            'email': result.get('email'),
            'phone': result.get('phone'),
            'location': result.get('location'),
            'bio': result.get('bio'),
            'profile_image': result.get('profile_image'),
            'cover_image': result.get('cover_image'),
            'marks_completed': result.get('marks_completed'),
            'riasec_completed': result.get('riasec_completed')
        }
        
        # Get marks data
        marks_data = get_user_marks(username)
        
        # Get RIASEC data
        riasec_data = get_user_riasec_results(username)
        
        return render_template('public_profile.html',
                             profile=profile,
                             marks_data=marks_data,
                             riasec_data=riasec_data,
                             get_trait_name=get_trait_name,
                             get_riasec_trait_description=get_riasec_trait_description,
                             is_public=True)
    except Exception as e:
        flash(f'Error loading profile: {str(e)}', 'error')
        return redirect(url_for('login'))

# API endpoint to check profile data is saved
@app.route('/api/profile', methods=['GET', 'POST'])
@login_required
def api_profile():
    if request.method == 'POST':
        try:
            data = request.json
            display_name = data.get('display_name')
            email = data.get('email')
            phone = data.get('phone')
            location = data.get('location')
            bio = data.get('bio')
            
            if not driver:
                return jsonify({'success': False, 'message': 'Database error'})
            
            with driver.session(database=NEO4J_DATABASE) as s:
                s.run("""
                    MATCH (u:User {username: $username})
                    SET u.display_name = $display_name,
                        u.email = $email,
                        u.phone = $phone,
                        u.location = $location,
                        u.bio = $bio
                """, 
                username=session['username'],
                display_name=display_name,
                email=email,
                phone=phone,
                location=location,
                bio=bio)
            
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})
    else:
        # GET request - return profile data
        profile = get_user_profile(session['username'])
        return jsonify(profile)

@app.route('/riasec/results')
@login_required
def riasec_results():
    """Detailed RIASEC results page"""
    # Check if user has completed both steps
    profile = get_user_profile(session['username'])
    if not profile or not profile.get('marks_completed'):
        flash('Please complete your marks entry first!', 'warning')
        return redirect(url_for('marks'))
    
    riasec_data = get_user_riasec_results(session['username'])
    
    if not riasec_data:
        flash('Please complete the RIASEC assessment first.', 'warning')
        return redirect(url_for('survey'))
    
    return render_template('riasec_results.html',
                         username=session['username'],
                         riasec_data=riasec_data,
                         get_trait_name=get_trait_name,
                         get_riasec_trait_description=get_riasec_trait_description)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)