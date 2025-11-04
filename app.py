"""
╔══════════════════════════════════════════════════════════════════════════╗
║                                                                          ║
║   JAIN UNIVERSITY COURSE & CAREER ADVISOR - FLASK APPLICATION (FIXED)   ║
║                          v5.0 With Chat Persistence                     ║
║                                                                          ║
║   FIXES:                                                                 ║
║   ✅ Chat history now persists across sessions                          ║
║   ✅ Current semester displayed in assistant                            ║
║   ✅ Profile data passed to assistant page                              ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import os
import uuid
import json
import re
from datetime import datetime
from functools import wraps
import pytz
import pandas as pd
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import plotly
import plotly.graph_objects as go

# ==================== CONFIGURATION ====================

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "jain-university-secret-key-2025")

app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False

UPLOAD_FOLDER = 'static/uploads/notifications'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "12")

# Database configuration
try:
    from utils_def_1 import (
        driver, NEO4J_DATABASE, get_mistral_client, mistral_request,
        MISTRAL_MODEL, MISTRAL_API_KEY, embedding_model, EMBED_DIM
    )
except ImportError as e:
    print(f"Warning: Could not import utilities: {e}")
    driver = None
    NEO4J_DATABASE = "neo4j"
    MISTRAL_API_KEY = None

try:
    from util_func_1 import (
        process_user_query, generate_response, SlidingWindowMemory,
        save_chat_message, load_chat_history, clear_chat_history,
        get_user_profile, save_user_profile, save_marks, get_user_marks,
        delete_mark, update_mark, update_marks_completed,
        get_user_riasec_results, save_riasec_results, calculate_riasec_scores,
        get_trait_name, get_riasec_trait_description, get_user_playlist,
        add_to_playlist, remove_from_playlist, get_playlist_count,
        extract_all_course_properties, format_course_for_display,
        format_courses_for_chat_response, save_user_semester
    )
except ImportError as e:
    print(f"Warning: Could not import functions: {e}")

# ==================== CONSTANTS ====================

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

# ==================== DECORATORS ====================

def login_required(f):
    """Decorator to require user login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            if request.path.startswith('/api/'):
                return jsonify({
                    'success': False,
                    'message': 'Authentication required. Please login.'
                }), 401
            
            flash('Please login first!', 'warning')
            return redirect(url_for('login'))
        
        return f(*args, **kwargs)
    
    return decorated_function

def admin_required(f):
    """Decorator to require admin login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session or not session.get('admin_logged_in'):
            flash('Admin access required!', 'error')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# ==================== AUTHENTICATION ROUTES ====================

@app.route('/')
def index():
    """Home page - redirect to login or home"""
    if 'username' in session:
        return redirect(url_for('home'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login route"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
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
                
                marks_completed = result.get("marks_completed", False)
                riasec_completed = result.get("riasec_completed", False)
                
                if not marks_completed:
                    flash('Welcome! Please enter your academic marks to get started.', 'info')
                    return redirect(url_for('marks'))
                elif not riasec_completed:
                    flash('Great! Now complete the career assessment to get personalized recommendations.', 'info')
                    return redirect(url_for('survey'))
                else:
                    flash('Welcome back!', 'success')
                    return redirect(url_for('home'))
            else:
                flash('Invalid username or password!', 'error')
        except Exception as e:
            flash(f'Login error: {str(e)}', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration route"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not username or not password:
            flash('Username and password required!', 'error')
            return render_template('register.html')
        
        if len(username) < 3:
            flash('Username must be at least 3 characters!', 'error')
            return render_template('register.html')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters!', 'error')
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
                
                s.run("""
                    CREATE (u:User {
                        username: $username, 
                        password: $password, 
                        email: $email,
                        display_name: $display_name,
                        created_at: datetime(),
                        marks_completed: false,
                        riasec_completed: false,
                        current_semester: 1,
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
            flash(f'Registration error: {str(e)}', 'error')
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    """User logout route"""
    username = session.get('username', 'User')
    session.clear()
    flash(f'Logged out successfully!', 'success')
    return redirect(url_for('login'))

# ==================== DASHBOARD ROUTES ====================

@app.route('/home')
@login_required
def home():
    """User home/dashboard"""
    try:
        profile = get_user_profile(session['username'])
        marks_data = get_user_marks(session['username']) or []
        riasec_data = get_user_riasec_results(session['username'])
        
        marks_completed = profile and profile.get('marks_completed', False)
        riasec_completed = profile and profile.get('riasec_completed', False)
        
        avg_score = 0
        if marks_data:
            avg_score = sum(m['percentage'] for m in marks_data) / len(marks_data)
        
        stats = {
            'completion': 100 if (marks_completed and riasec_completed) else 50 if marks_completed else 0,
            'subjects_count': len(marks_data),
            'average_score': avg_score,
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
    except Exception as e:
        print(f"Error in home route: {str(e)}")
        flash(f'Error loading home: {str(e)}', 'error')
        return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Dashboard with RIASEC visualization"""
    try:
        if not driver:
            flash('Database connection error!', 'error')
            return redirect(url_for('home'))
        
        profile = get_user_profile(session['username'])
        if not profile or not profile.get('marks_completed', False):
            flash('Please complete your marks entry first!', 'warning')
            return redirect(url_for('marks'))
        
        if not profile.get('riasec_completed', False):
            flash('Please complete the RIASEC assessment first!', 'warning')
            return redirect(url_for('survey'))
        
        riasec_data = get_user_riasec_results(session['username'])
        
        if not riasec_data:
            flash('Please complete the RIASEC assessment first.', 'warning')
            return redirect(url_for('survey'))

        scores = riasec_data.get('scores', {})
        top3 = riasec_data.get('top3', [])
        timestamp = riasec_data.get('timestamp', 'Unknown')

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
                radialaxis=dict(visible=True, range=[0, 100], tickfont=dict(size=10)),
                angularaxis=dict(tickfont=dict(size=11))
            ),
            showlegend=False,
            height=400,
            margin=dict(l=50, r=50, t=50, b=50)
        )

        chart_json = plotly.io.to_json(fig)
        marks_data = get_user_marks(session['username']) or []
        
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
    except Exception as e:
        print(f"Error in dashboard route: {str(e)}")
        flash(f'Error loading dashboard: {str(e)}', 'error')
        return redirect(url_for('home'))

# ==================== MARKS ROUTES ====================

@app.route('/marks', methods=['GET', 'POST'])
@login_required
def marks():
    """Marks management and tracking"""
    if request.method == 'POST':
        try:
            if 'add_marks' in request.form:
                subject = request.form.get('subject', '').strip()
                marks_scored = float(request.form.get('marks_scored', 0))
                total_marks = float(request.form.get('total_marks', 100))
                
                if not subject:
                    flash('Please select or enter a valid subject name!', 'error')
                elif marks_scored < 0 or total_marks < 0:
                    flash('Marks cannot be negative!', 'error')
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
                marks_data = get_user_marks(session['username']) or []
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
                marks_scored = float(request.form.get('marks_scored', 0))
                total_marks = float(request.form.get('total_marks', 100))
                
                if marks_scored > total_marks:
                    flash('Marks cannot exceed total!', 'error')
                else:
                    if update_mark(mark_id, marks_scored, total_marks):
                        flash('Mark updated successfully!', 'success')
                    else:
                        flash('Error updating mark!', 'error')
        except ValueError:
            flash('Please enter valid numbers for marks!', 'error')
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
    
    marks_data = get_user_marks(session['username']) or []
    profile = get_user_profile(session['username'])
    marks_completed = profile and profile.get('marks_completed', False)
    
    return render_template('marks.html', 
                        marks_data=marks_data,
                        default_subjects=DEFAULT_SUBJECTS,
                        username=session['username'],
                        marks_completed=marks_completed)

# ==================== RIASEC ROUTES ====================

@app.route('/survey', methods=['GET', 'POST'])
@login_required
def survey():
    """RIASEC career assessment survey"""
    if request.method == 'POST':
        try:
            data = request.get_json()
            answers = data.get('answers', {})
            
            if not answers:
                return jsonify({'success': False, 'message': 'No answers provided'}), 400
            
            riasec_results = calculate_riasec_scores(answers)
            username = session['username']
            success = save_riasec_results(username, answers, riasec_results)
            
            if success:
                return jsonify({'success': True, 'message': 'RIASEC results saved successfully'})
            else:
                return jsonify({'success': False, 'message': 'Error saving results to database'}), 500
        
        except Exception as e:
            print(f"Error in survey: {str(e)}")
            return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500
    
    riasec_data = get_user_riasec_results(session['username'])
    
    if riasec_data:
        flash('You can review your previous results or retake the assessment.', 'info')
    
    return render_template('survey.html', 
                        username=session['username'],
                        riasec_data=riasec_data,
                        get_trait_name=get_trait_name,
                        riasec_questions=RIASEC_QUESTIONS)

@app.route('/riasec/results')
@login_required
def riasec_results():
    """View RIASEC results"""
    try:
        profile = get_user_profile(session['username'])
        if not profile or not profile.get('marks_completed', False):
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
    except Exception as e:
        print(f"Error in riasec_results: {str(e)}")
        flash(f'Error loading RIASEC results: {str(e)}', 'error')
        return redirect(url_for('home'))

# ==================== CHAT ROUTES (FIXED!) ====================

@app.route('/assistant')
@login_required
def assistant():
    """AI Chat assistant interface - FIXED with profile data"""
    try:
        username = session['username']
        
        # Get user profile with semester info
        profile = get_user_profile(username)
        if not profile or not profile.get('marks_completed', False):
            flash('Please complete your marks entry first to get personalized recommendations!', 'warning')
            return redirect(url_for('marks'))
        
        if not profile.get('riasec_completed', False):
            flash('Please complete the RIASEC assessment to get career-specific advice!', 'warning')
            return redirect(url_for('survey'))
        
        # Load existing chat history from database
        chat_messages = load_chat_history(username) or []
        
        # Get current semester from profile
        current_semester = profile.get('current_semester', 1)
        display_name = profile.get('display_name', username)
        
        return render_template('assistant.html',
                            username=username,
                            display_name=display_name,
                            current_semester=current_semester,
                            profile=profile,
                            chat_messages=chat_messages,
                            driver_connected=bool(driver),
                            mistral_available=bool(MISTRAL_API_KEY))
    except Exception as e:
        print(f"Error in assistant: {str(e)}")
        flash(f'Error loading assistant: {str(e)}', 'error')
        return redirect(url_for('home'))

@app.route('/chat/send', methods=['POST'])
@login_required
def send_chat():
    """Send chat message and get AI response"""
    try:
        user_input = request.json.get('message', '').strip()
        if not user_input:
            return jsonify({'error': 'No message provided'}), 400
        
        username = session['username']
        
        # Save user message to database
        save_chat_message(username, "user", user_input)
        
        input_lower = user_input.lower()
        is_prereq_query = any(term in input_lower for term in [
            'prerequisite', 'prereq', 'pre-req', 'dependency', 'require', 'before', 'pre reqs', 'pre recs'
        ])
        is_postreq_query = any(term in input_lower for term in [
            'postrequisite', 'postreq', 'post-req', 'leads to', 'next', 'after', 'post recs', 'post reqs', 'post req'
        ])
        is_pathway_query = any(term in input_lower for term in [
            'pathway', 'learning path', 'study path', 'progression', 'roadmap', 'journey', 'complete path', 'full path'
        ])
        
        query_results = process_user_query(driver, user_input, username)
        tree = query_results.get('ascii_tree') if query_results else None
        
        if (is_prereq_query or is_postreq_query or is_pathway_query) and tree:
            save_chat_message(username, "assistant", tree, is_code=True)
            send_tree = tree
        else:
            send_tree = None
        
        client = get_mistral_client(MISTRAL_API_KEY) if MISTRAL_API_KEY else None
        
        # Load full chat history from database
        chat_history = load_chat_history(username) or []
        
        assistant_response = generate_response(
            query_results=query_results or {},
            user_input=user_input,
            client=client,
            conversation_history=chat_history,
            _drv=driver,
            database_name=NEO4J_DATABASE,
            username=username
        )
        
        # Save assistant response to database
        save_chat_message(username, "assistant", assistant_response)
        
        courses_data = []
        if query_results and query_results.get('courses'):
            courses_data = format_courses_for_chat_response(query_results['courses'])
        
        return jsonify({
            'success': True,
            'response': assistant_response,
            'ascii_tree': send_tree,
            'courses': courses_data,
            'courses_count': len(query_results.get('courses', [])) if query_results else 0,
            'jobs_count': len(query_results.get('jobs', [])) if query_results else 0
        })
    
    except Exception as e:
        print(f"Error in send_chat: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/chat/clear', methods=['POST'])
@login_required
def clear_chat():
    """Clear chat history"""
    try:
        clear_chat_history(session['username'])
        return jsonify({'success': True, 'message': 'Chat history cleared'})
    except Exception as e:
        print(f"Error in clear_chat: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== PLAYLIST ROUTES ====================

@app.route('/api/playlist', methods=['GET'])
@login_required
def get_playlist_api():
    """Get user's playlist"""
    try:
        playlist = get_user_playlist(session['username']) or []
        return jsonify({
            'success': True,
            'courses': playlist,
            'count': len(playlist)
        })
    except Exception as e:
        print(f"Error in get_playlist_api: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e),
            'courses': [],
            'count': 0
        }), 500

@app.route('/api/playlist/add', methods=['POST'])
@login_required
def add_to_playlist_api():
    """Add course to playlist"""
    try:
        data = request.get_json()
        username = session.get("username")
        course_code = data.get("course_code", '').strip() if data else ''

        if not username:
            return jsonify({'success': False, 'message': 'User not logged in'}), 401

        if not course_code:
            return jsonify({'success': False, 'message': 'Course code required'}), 400

        result = add_to_playlist(username, course_code)
        return jsonify(result), 200

    except Exception as e:
        print(f"Error in add_to_playlist_api: {str(e)}")
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500

@app.route('/api/playlist/remove', methods=['POST'])
@login_required
def remove_from_playlist_api():
    """Remove course from playlist"""
    try:
        data = request.json
        course_code = data.get('course_code', '').strip() if data else ''

        if not course_code:
            return jsonify({'success': False, 'message': 'Course code required'}), 400

        result = remove_from_playlist(session['username'], course_code)
        return jsonify(result), 200

    except Exception as e:
        print(f"Error in remove_from_playlist_api: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/playlist/count', methods=['GET'])
@login_required
def get_playlist_count_api():
    """Get playlist course count"""
    try:
        count = get_playlist_count(session['username']) or 0
        return jsonify({'success': True, 'count': count}), 200
    except Exception as e:
        print(f"Error in get_playlist_count_api: {str(e)}")
        return jsonify({'success': False, 'count': 0}), 500

# ==================== PROFILE ROUTES ====================

@app.route('/profile')
@login_required
def profile():
    """User profile page - FIXED with better error handling"""
    try:
        username = session.get('username')
        
        if not username:
            flash('Session error. Please login again.', 'error')
            return redirect(url_for('login'))
        
        # Get all data with proper null checks
        user_profile = get_user_profile(username) or {}
        marks_data = get_user_marks(username) or []
        riasec_data = get_user_riasec_results(username) or {}
        playlist_data = get_user_playlist(username) or []
        
        # Provide defaults for all template variables
        return render_template('profile.html',
                            username=username,
                            profile_data=user_profile if user_profile else {},
                            marks_data=marks_data,
                            riasec_data=riasec_data,
                            playlist_data=playlist_data,
                            get_trait_name=get_trait_name,
                            get_riasec_trait_description=get_riasec_trait_description)
    
    except TypeError as e:
        print(f"TypeError in profile route: {str(e)}")
        flash(f'Error: NoneType object error - {str(e)}', 'error')
        return redirect(url_for('home'))
    
    except Exception as e:
        print(f"Error in profile route: {str(e)}")
        flash(f'Error loading profile: {str(e)}', 'error')
        return redirect(url_for('home'))

@app.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    """Update user profile"""
    try:
        username = session.get('username')
        
        display_name = request.form.get('display_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        location = request.form.get('location', '').strip()
        bio = request.form.get('bio', '').strip()
        current_semester = request.form.get('current_semester', '').strip()
        
        success = True
        if display_name:
            result = save_user_profile(username, 'display_name', display_name)
            success = success and result
        if email:
            result = save_user_profile(username, 'email', email)
            success = success and result
        if phone:
            result = save_user_profile(username, 'phone', phone)
            success = success and result
        if location:
            result = save_user_profile(username, 'location', location)
            success = success and result
        if bio:
            result = save_user_profile(username, 'bio', bio)
            success = success and result
        if current_semester:
            result = save_user_semester(username, current_semester)
            success = success and result
        
        if success:
            flash('Profile updated successfully!', 'success')
        else:
            flash('Error updating profile!', 'error')
        
        return redirect(url_for('profile'))
    except Exception as e:
        print(f"Error in update_profile: {str(e)}")
        flash(f'Error updating profile: {str(e)}', 'error')
        return redirect(url_for('profile'))

# ==================== ADMIN ROUTES ====================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page"""
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            session['admin_username'] = username
            flash('Admin login successful!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid admin credentials!', 'error')
    
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    """Admin logout"""
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    flash('Admin logged out!', 'success')
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    """Admin dashboard with statistics"""
    try:
        if not driver:
            flash('Database connection error!', 'error')
            return redirect(url_for('admin_login'))
        
        with driver.session(database=NEO4J_DATABASE) as s:
            total_users_result = s.run("MATCH (u:User) RETURN count(u) as count").single()
            marks_result = s.run("MATCH (u:User) WHERE u.marks_completed = true RETURN count(u) as count").single()
            riasec_result = s.run("MATCH (u:User) WHERE u.riasec_completed = true RETURN count(u) as count").single()
            messages_result = s.run("MATCH (m:ChatMessage) RETURN count(m) as count").single()
            courses_result = s.run("MATCH (c:Course) RETURN count(c) as count").single()
            
            total_users = total_users_result['count'] if total_users_result else 0
            marks_completed = marks_result['count'] if marks_result else 0
            riasec_completed = riasec_result['count'] if riasec_result else 0
            total_messages = messages_result['count'] if messages_result else 0
            total_courses = courses_result['count'] if courses_result else 0
            
            recent_users = s.run("""
                MATCH (u:User) 
                RETURN u.username as username, u.display_name as display_name,
                       u.email as email, u.created_at as created_at,
                       u.marks_completed as marks_completed, u.riasec_completed as riasec_completed
                ORDER BY u.created_at DESC LIMIT 10
            """).data() or []
        
        stats = {
            'total_users': total_users,
            'marks_completed': marks_completed,
            'riasec_completed': riasec_completed,
            'total_messages': total_messages,
            'total_courses': total_courses,
            'completion_rate': round((riasec_completed / total_users * 100) if total_users > 0 else 0, 1),
            'marks_rate': round((marks_completed / total_users * 100) if total_users > 0 else 0, 1)
        }
        
        return render_template('admin_dashboard.html', stats=stats, recent_users=recent_users)
    except Exception as e:
        print(f"Error in admin_dashboard: {str(e)}")
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('admin_login'))

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    """404 error handler"""
    return render_template('error.html', error='Page not found'), 404

@app.errorhandler(500)
def server_error(error):
    """500 error handler"""
    return render_template('error.html', error='Server error'), 500

@app.errorhandler(403)
def forbidden(error):
    """403 error handler"""
    return render_template('error.html', error='Access forbidden'), 403

# ==================== CONTEXT PROCESSORS ====================

@app.context_processor
def inject_user():
    """Inject user info into all templates"""
    return {
        'current_user': session.get('username'),
        'is_logged_in': 'username' in session,
        'is_admin': session.get('admin_logged_in', False)
    }

# ==================== DEBUG & RUN ====================

if __name__ == '__main__':
    print("\n" + "=" * 80)
    print("JAIN UNIVERSITY COURSE & CAREER ADVISOR - FIXED v5.0")
    print("=" * 80)
    print(f"✓ Database Connection: {bool(driver)}")
    print(f"✓ Mistral API Key: {bool(MISTRAL_API_KEY)}")
    print("=" * 80 + "\n")
    
    try:
        app.run(
            debug=True,
            host='0.0.0.0',
            port=5000,
            use_reloader=True,
            use_debugger=True
        )
    except KeyboardInterrupt:
        print("\n\nApplication stopped by user")
    except Exception as e:
        print(f"\nError starting application: {e}")