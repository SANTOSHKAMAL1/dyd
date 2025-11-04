"""
Jain University Course & Career Advisor - Core Functions Module
ENHANCED VERSION: Playlist, Semester, and Career Planning Features
"""

import json
import os
import re
import uuid
from typing import List, Dict, Any, Optional
import numpy as np
import pytz
from datetime import datetime
from neo4j import GraphDatabase
import pandas as pd

from utils_def_1 import (
    embedding_model, run_read_cypher, mistral_request, 
    MISTRAL_MODEL, driver, MISTRAL_API_KEY, get_mistral_client,
    NEO4J_DATABASE
)

# ============================================================================
# COURSE PROPERTIES CONSTANTS
# ============================================================================

COURSE_PROPERTIES = [
    'course_code', 'course_title', 'description', 'credits', 'level',
    'department', 'semester', 'category', 'duration', 'instructor',
    'subject_area', 'prereq_course_codes', 'course_riasec_vector',
    'R', 'I', 'A', 'S', 'E', 'C', 'recommended_semester'
]

# ============================================================================
# DATABASE HELPER FUNCTIONS
# ============================================================================

def save_chat_message(username, role, content, is_code=False):
    """Save a single chat message to Neo4j"""
    if not driver:
        return None
    try:
        india_tz = pytz.timezone("Asia/Kolkata")
        now_india = datetime.now(india_tz).isoformat()
        with driver.session(database=NEO4J_DATABASE) as s:
            result = s.run("""
                MATCH (u:User {username: $username})
                CREATE (m:ChatMessage {
                    id: $msg_id,
                    role: $role,
                    content: $content,
                    is_code: $is_code,
                    timestamp: datetime($timestamp)
                })
                CREATE (u)-[:HAS_MESSAGE]->(m)
                RETURN m.timestamp AS timestamp  
            """, username=username, msg_id=str(uuid.uuid4()),
                       role=role, content=content, is_code=is_code,
                       timestamp=now_india).single()
            return result["timestamp"] if result else None
    except Exception as e:
        print(f"Failed to save message: {e}")
        return None

def load_chat_history(username):
    """Load chat history from Neo4j"""
    if not driver:
        return []
    try:
        with driver.session(database=NEO4J_DATABASE) as s:
            result = s.run("""
                MATCH (u:User {username: $username})-[:HAS_MESSAGE]->(m:ChatMessage)
                RETURN m.role AS role, 
                       m.content AS content, 
                       m.is_code AS is_code,
                       m.timestamp AS timestamp  
                ORDER BY m.timestamp ASC
            """, username=username)
            messages = []
            for record in result:
                msg = {
                    "role": record["role"],
                    "content": record["content"],
                    "timestamp": record["timestamp"]
                }
                if record.get("is_code"):
                    msg["is_code"] = True
                messages.append(msg)
            return messages
    except Exception as e:
        print(f"Error loading chat history: {e}")
        return []

def clear_chat_history(username):
    """Clear chat history from Neo4j"""
    if not driver:
        return
    try:
        with driver.session(database=NEO4J_DATABASE) as s:
            s.run("""
                MATCH (u:User {username: $username})-[:HAS_MESSAGE]->(m:ChatMessage)
                DETACH DELETE m
            """, username=username)
    except Exception as e:
        print(f"Failed to clear chat history: {e}")

# ============================================================================
# USER PROFILE FUNCTIONS
# ============================================================================

def get_user_profile(username):
    """Get complete user profile from Neo4j"""
    if not driver:
        return None
    try:
        with driver.session(database=NEO4J_DATABASE) as s:
            result = s.run("""
                MATCH (u:User {username: $username})
                OPTIONAL MATCH (u)-[:HAS_MARK]->(m:Mark)
                WITH u, count(m) as marks_count
                RETURN u.username AS username,
                       u.email AS email,
                       u.display_name AS display_name,
                       u.bio AS bio,
                       u.location AS location,
                       u.phone AS phone,
                       u.profile_picture AS profile_picture,
                       u.created_at AS created_at,
                       u.current_semester AS current_semester,
                       u.riasec_completed AS riasec_completed,
                       u.marks_completed AS marks_completed,
                       u.riasec_top3 AS top3,
                       marks_count
            """, username=username).single()
        return result
    except Exception as e:
        print(f"Error loading profile: {e}")
        return None

def save_user_profile(username, field, value):
    """Save user profile information to Neo4j"""
    if not driver:
        return False
    try:
        with driver.session(database=NEO4J_DATABASE) as s:
            s.run(f"""
                MATCH (u:User {{username: $username}})
                SET u.{field} = $value
            """, username=username, value=value)
        return True
    except Exception as e:
        print(f"Error saving profile: {e}")
        return False

def save_user_semester(username, semester):
    """Save user's current semester selection"""
    if not driver:
        return False
    try:
        with driver.session(database=NEO4J_DATABASE) as s:
            s.run("""
                MATCH (u:User {username: $username})
                SET u.current_semester = $semester
            """, username=username, semester=int(semester))
        return True
    except Exception as e:
        print(f"Error saving semester: {e}")
        return False

# ============================================================================
# MARKS MANAGEMENT FUNCTIONS
# ============================================================================

def save_marks(username, subject, marks_scored, total_marks):
    """Save marks to Neo4j"""
    if not driver:
        return False
    try:
        with driver.session(database=NEO4J_DATABASE) as s:
            existing = s.run("""
                MATCH (u:User {username: $username})-[:HAS_MARK]->(m:Mark {subject: $subject})
                RETURN m.id AS id
            """, username=username, subject=subject).single()

            if existing:
                return "exists"

        percentage = round((marks_scored / total_marks) * 100, 2)
        with driver.session(database=NEO4J_DATABASE) as s:
            s.run("""
                MATCH (u:User {username: $username})
                CREATE (m:Mark {
                    id: $mark_id,
                    subject: $subject,
                    marks_scored: $marks_scored,
                    total_marks: $total_marks,
                    percentage: $percentage,
                    timestamp: datetime()
                })
                CREATE (u)-[:HAS_MARK]->(m)
            """, username=username, mark_id=str(uuid.uuid4()),
                  subject=subject, marks_scored=marks_scored,
                  total_marks=total_marks, percentage=percentage)
        return True
    except Exception as e:
        print(f"Error saving marks: {e}")
        return False

def get_user_marks(username):
    """Get all marks for a user from Neo4j"""
    if not driver:
        return []
    try:
        with driver.session(database=NEO4J_DATABASE) as s:
            result = s.run("""
                MATCH (u:User {username: $username})-[:HAS_MARK]->(m:Mark)
                RETURN m.id AS id, m.subject AS subject, 
                       m.marks_scored AS marks_scored,
                       m.total_marks AS total_marks, 
                       m.percentage AS percentage,
                       toString(m.timestamp) AS timestamp
                ORDER BY m.timestamp DESC
            """, username=username)
            return [dict(record) for record in result]
    except Exception as e:
        print(f"Error loading marks: {e}")
        return []

def delete_mark(mark_id):
    """Delete a mark entry from Neo4j"""
    if not driver:
        return False
    try:
        with driver.session(database=NEO4J_DATABASE) as s:
            s.run("""
                MATCH (m:Mark {id: $mark_id})
                DETACH DELETE m
            """, mark_id=mark_id)
        return True
    except Exception as e:
        print(f"Error deleting mark: {e}")
        return False

def update_mark(mark_id, marks_scored, total_marks):
    """Update an existing mark in Neo4j"""
    if not driver:
        return False
    try:
        percentage = round((marks_scored / total_marks) * 100, 2)
        with driver.session(database=NEO4J_DATABASE) as s:
            s.run("""
                MATCH (m:Mark {id: $mark_id})
                SET m.marks_scored = $marks_scored,
                    m.total_marks = $total_marks,
                    m.percentage = $percentage,
                    m.timestamp = datetime()
            """, mark_id=mark_id, marks_scored=marks_scored,
                  total_marks=total_marks, percentage=percentage)
        return True
    except Exception as e:
        print(f"Error updating mark: {e}")
        return False

def update_marks_completed(username):
    """Mark that user has completed marks entry in Neo4j"""
    if not driver:
        return
    try:
        with driver.session(database=NEO4J_DATABASE) as s:
            s.run("""
                MATCH (u:User {username: $username})
                SET u.marks_completed = true
            """, username=username)
    except Exception as e:
        print(f"Error updating marks status: {e}")

# ============================================================================
# RIASEC FUNCTIONS
# ============================================================================

def save_riasec_results(username, answers, riasec_results):
    """Save complete RIASEC results to Neo4j"""
    if not driver:
        return False
    
    try:
        with driver.session(database=NEO4J_DATABASE) as s:
            s.run("""
                MATCH (u:User {username: $username})
                SET u.riasec_answers = $answers,
                    u.riasec_scores = $scores,
                    u.riasec_top3 = $top3,
                    u.riasec_vector = $vector,
                    u.riasec_completed = true,
                    u.riasec_timestamp = datetime()
            """, 
            username=username,
            answers=json.dumps(answers),
            scores=json.dumps(riasec_results['scores']),
            top3=riasec_results['top3'],
            vector=riasec_results['riasec_vector'])
        
        print(f"RIASEC results saved for user: {username}")
        return True
    except Exception as e:
        print(f"Error saving RIASEC results: {e}")
        return False

def get_user_riasec_results(username):
    """Get complete RIASEC results from Neo4j"""
    if not driver:
        return None
    
    try:
        with driver.session(database=NEO4J_DATABASE) as s:
            result = s.run("""
                MATCH (u:User {username: $username})
                RETURN 
                    u.riasec_scores AS scores,
                    u.riasec_top3 AS top3,
                    u.riasec_answers AS answers,
                    u.riasec_vector AS vector,
                    toString(u.riasec_timestamp) AS timestamp,
                    u.riasec_completed AS completed
            """, username=username).single()
            
            if result and result.get("completed"):
                scores_data = {}
                if result["scores"]:
                    try:
                        scores_data = json.loads(result["scores"])
                    except:
                        scores_data = {}
                
                answers_data = {}
                if result["answers"]:
                    try:
                        answers_data = json.loads(result["answers"])
                    except:
                        answers_data = {}
                
                return {
                    'scores': scores_data,
                    'top3': result["top3"] if result["top3"] else [],
                    'answers': answers_data,
                    'vector': result["vector"] if result["vector"] else [],
                    'timestamp': result["timestamp"] if result["timestamp"] else "Unknown"
                }
            return None
    except Exception as e:
        print(f"Error loading RIASEC results: {e}")
        return None

def calculate_riasec_scores(answers):
    """Calculate RIASEC scores from user answers"""
    
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
    
    trait_responses = {'R': [], 'I': [], 'A': [], 'S': [], 'E': [], 'C': []}
    
    for question, trait in RIASEC_QUESTIONS:
        response = answers.get(question, 0)
        trait_responses[trait].append(response)
    
    scores = {}
    for trait, responses in trait_responses.items():
        if responses:
            scores[trait] = sum(responses) / len(responses)
        else:
            scores[trait] = 0.0
    
    total = sum(scores.values())
    if total > 0:
        for trait in scores:
            scores[trait] = scores[trait] / total
    
    top3 = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
    
    return {
        'scores': scores,
        'top3': [trait for trait, score in top3],
        'riasec_vector': [scores['R'], scores['I'], scores['A'], scores['S'], scores['E'], scores['C']]
    }

def get_trait_name(trait_code):
    """Get full name for RIASEC trait codes"""
    trait_names = {
        'R': 'Realistic',
        'I': 'Investigative', 
        'A': 'Artistic',
        'S': 'Social',
        'E': 'Enterprising',
        'C': 'Conventional'
    }
    return trait_names.get(trait_code, 'Unknown')

def get_riasec_trait_description(trait_code):
    """Get detailed description for RIASEC traits"""
    descriptions = {
        'R': {
            'name': 'Realistic',
            'description': 'Practical, physical, hands-on, tool-oriented people who enjoy working with machines, tools, plants and animals.',
            'skills': ['Manual dexterity', 'Technical skills', 'Mechanical ability', 'Physical coordination'],
            'work_env': 'Outdoor, hands-on, practical work environments',
            'common_careers': ['Engineer', 'Mechanic', 'Farmer', 'Police Officer', 'Military']
        },
        'I': {
            'name': 'Investigative',
            'description': 'Analytical, intellectual, scientific, explorative people who enjoy observation, investigation and problem-solving.',
            'skills': ['Analytical thinking', 'Research skills', 'Scientific reasoning', 'Problem-solving'],
            'work_env': 'Research labs, academic settings, scientific environments',
            'common_careers': ['Scientist', 'Researcher', 'Doctor', 'Programmer', 'Mathematician']
        },
        'A': {
            'name': 'Artistic',
            'description': 'Creative, original, intuitive, expressive people who enjoy creative activities like art, drama, crafts, dance, music, or creative writing.',
            'skills': ['Creativity', 'Imagination', 'Artistic ability', 'Originality'],
            'work_env': 'Unstructured environments allowing creative expression',
            'common_careers': ['Artist', 'Designer', 'Writer', 'Musician', 'Actor']
        },
        'S': {
            'name': 'Social',
            'description': 'Cooperative, supportive, helpful, empathetic people who enjoy working with people to educate, help, or serve them.',
            'skills': ['Communication', 'Empathy', 'Teaching ability', 'Interpersonal skills'],
            'work_env': 'Team-oriented, community-focused, helping environments',
            'common_careers': ['Teacher', 'Counselor', 'Nurse', 'Social Worker', 'Psychologist']
        },
        'E': {
            'name': 'Enterprising',
            'description': 'Persuasive, energetic, ambitious, risk-taking people who enjoy leadership roles, business activities, and influencing others.',
            'skills': ['Leadership', 'Persuasion', 'Negotiation', 'Strategic planning'],
            'work_env': 'Competitive, fast-paced, business-oriented environments',
            'common_careers': ['Entrepreneur', 'Manager', 'Lawyer', 'Sales Executive', 'Politician']
        },
        'C': {
            'name': 'Conventional',
            'description': 'Detail-oriented, organized, structured people who enjoy working with data, numbers, and systematic approaches to tasks.',
            'skills': ['Organization', 'Attention to detail', 'Numerical ability', 'Reliability'],
            'work_env': 'Structured, orderly, systematic work environments',
            'common_careers': ['Accountant', 'Banker', 'Administrator', 'Data Analyst', 'Office Manager']
        }
    }
    
    return descriptions.get(trait_code, {
        'name': 'Unknown',
        'description': 'No description available',
        'skills': [],
        'work_env': 'Unknown',
        'common_careers': []
    })

# ============================================================================
# MEMORY MANAGEMENT SYSTEM
# ============================================================================

class SlidingWindowMemory:
    def __init__(self, recent_messages_count=6, max_context_tokens=1500):
        self.recent_messages_count = recent_messages_count
        self.max_context_tokens = max_context_tokens

    def initialize_memory(self):
        return {
            'user_profile': {
                'name': None,
                'interests': {},
                'career_goals': {},
                'mentioned_courses': set()
            },
            'conversation_summary': "",
            'last_summarized_index': 0,
            'last_updated': datetime.now(pytz.timezone("Asia/Kolkata")).isoformat()
        }

    def extract_user_profile(self, messages: List[Dict]) -> Dict:
        memory = self.initialize_memory()
        profile = memory['user_profile']

        for msg in messages:
            if msg['role'] != 'user':
                continue

            content = msg['content']
            content_lower = content.lower()

            if not profile['name']:
                name_patterns = [
                    r'my name is (\w+)',
                    r'i am (\w+)(?:\s|$|[,.])',
                    r'i\'m (\w+)(?:\s|$|[,.])',
                    r'call me (\w+)'
                ]

                for pattern in name_patterns:
                    match = re.search(pattern, content_lower)
                    if match:
                        name = match.group(1).strip()
                        if (len(name) > 1 and name.isalpha() and
                                name.lower() not in ['interested', 'learning', 'studying']):
                            profile['name'] = name.title()
                            break

            interest_patterns = [
                (r'interested in ([^.!?\n]+)', 0.9),
                (r'want to learn (?:about )?([^.!?\n]+)', 0.8),
                (r'studying ([^.!?\n]+)', 0.85),
                (r'passionate about ([^.!?\n]+)', 0.95)
            ]

            for pattern, confidence in interest_patterns:
                matches = re.findall(pattern, content_lower)
                for match in matches:
                    interest = match.strip()
                    if interest and len(interest) > 2 and len(interest) < 50:
                        profile['interests'][interest] = max(
                            profile['interests'].get(interest, 0),
                            confidence
                        )

            course_codes = re.findall(r'\b([A-Z]{2,4}[-\s]?\d{2,3})\b', content)
            for code in course_codes:
                profile['mentioned_courses'].add(code.upper().replace(' ', '-'))

        return profile

    def build_context(self, messages: List[Dict], current_query: str, client=None, username=None) -> str:
        memory = self.initialize_memory()
        profile = self.extract_user_profile(messages)

        context_parts = []
        user_message_count = sum(1 for msg in messages if msg['role'] == 'user' and not msg.get('is_code'))

        # Add user's display name from profile
        if username and driver:
            try:
                with driver.session(database=NEO4J_DATABASE) as s:
                    result = s.run("""
                        MATCH (u:User {username: $username})
                        RETURN u.display_name AS display_name
                    """, username=username).single()
                    if result and result['display_name']:
                        context_parts.append(f"USER NAME: {result['display_name']}")
            except:
                pass

        if user_message_count <= 1:
            context_parts.append("SESSION: First message")
        else:
            context_parts.append(f"SESSION: {user_message_count} messages so far")

        if profile['name'] or profile['interests'] or profile['career_goals']:
            profile_lines = ["STUDENT PROFILE:"]
            if profile['name']:
                profile_lines.append(f"Name: {profile['name']}")
            if profile['interests']:
                top_interests = sorted(profile['interests'].items(), key=lambda x: x[1], reverse=True)[:3]
                interests_str = ', '.join([i for i, _ in top_interests])
                profile_lines.append(f"Interests: {interests_str}")
            if profile['mentioned_courses']:
                courses_str = ', '.join(list(profile['mentioned_courses'])[-3:])
                profile_lines.append(f"Courses discussed: {courses_str}")

            context_parts.append('\n'.join(profile_lines))

        if len(messages) > self.recent_messages_count:
            recent_msgs = messages[-self.recent_messages_count:]
            if recent_msgs:
                recent_lines = ["RECENT MESSAGES:"]
                for msg in recent_msgs:
                    if msg.get('is_code'):
                        continue
                    role = "Student" if msg['role'] == 'user' else "Assistant"
                    content = msg['content']
                    if len(content) > 150:
                        content = content[:150] + "..."
                    recent_lines.append(f"{role}: {content}")

                context_parts.append('\n'.join(recent_lines))
        else:
            if messages:
                msg_lines = ["CONVERSATION HISTORY:"]
                for msg in messages:
                    if msg.get('is_code'):
                        continue
                    role = "Student" if msg['role'] == 'user' else "Assistant"
                    content = msg['content']
                    if len(content) > 150:
                        content = content[:150] + "..."
                    msg_lines.append(f"{role}: {content}")

                context_parts.append('\n'.join(msg_lines))

        return '\n\n'.join(context_parts)

# ============================================================================
# PLAYLIST FUNCTIONS - ENHANCED WITH SEMESTER AND FULL DETAILS
# ============================================================================

def get_user_playlist(username, semester=None):
    """Get all courses in user's playlist from Neo4j with full details and optional semester filter"""
    if not driver:
        return []
    try:
        with driver.session(database=NEO4J_DATABASE) as s:
            if semester:
                # Filter by semester
                result = s.run("""
                    MATCH (u:User {username: $username})-[:HAS_PLAYLIST]->(p:Playlist)-[:CONTAINS]->(c:Course)
                    WHERE c.recommended_semester = $semester OR c.recommended_semester CONTAINS $sem_str
                    RETURN c.course_code AS course_code,
                           c.course_title AS course_title,
                           c.subject_area AS subject_area,
                           c.credits AS credits,
                           c.level AS level,
                           c.department AS department,
                           c.description AS description,
                           c.prereq_course_codes AS prerequisites,
                           c.recommended_semester AS recommended_semester,
                           c.category AS category,
                           c.duration AS duration,
                           c.instructor AS instructor,
                           c.R AS R, c.I AS I, c.A AS A, c.S AS S, c.E AS E, c.C AS C,
                           c.course_riasec_vector AS course_riasec_vector
                    ORDER BY c.course_code
                """, username=username, semester=int(semester), sem_str=str(semester))
            else:
                # Get all courses
                result = s.run("""
                    MATCH (u:User {username: $username})-[:HAS_PLAYLIST]->(p:Playlist)-[:CONTAINS]->(c:Course)
                    RETURN c.course_code AS course_code,
                           c.course_title AS course_title,
                           c.subject_area AS subject_area,
                           c.credits AS credits,
                           c.level AS level,
                           c.department AS department,
                           c.description AS description,
                           c.prereq_course_codes AS prerequisites,
                           c.recommended_semester AS recommended_semester,
                           c.category AS category,
                           c.duration AS duration,
                           c.instructor AS instructor,
                           c.R AS R, c.I AS I, c.A AS A, c.S AS S, c.E AS E, c.C AS C,
                           c.course_riasec_vector AS course_riasec_vector
                    ORDER BY c.recommended_semester, c.course_code
                """, username=username)
            
            courses = []
            for record in result:
                course_dict = dict(record)
                courses.append(course_dict)
            return courses
    except Exception as e:
        print(f"Error loading playlist: {e}")
        return []

def add_to_playlist(username, course_code):
    """Add a course to user's playlist with all details"""
    print("🔹 [START] add_to_playlist called")
    print(f"🔹 Username: {username}, Course code: {course_code}")

    if not driver:
        print("❌ Neo4j driver not initialized")
        return {"success": False, "message": "Database connection error"}

    try:
        playlist_id = f"{username}_playlist"
        print(f"🔹 Computed playlist_id: {playlist_id}")

        with driver.session(database=NEO4J_DATABASE) as s:
            print("🔹 Checking if course exists...")
            course_check = s.run("""
                MATCH (c:Course {course_code: $course_code})
                RETURN c.course_code AS code, 
                       c.course_title AS title,
                       c.credits AS credits,
                       c.recommended_semester AS semester
            """, course_code=course_code).single()

            if not course_check:
                print("❌ Course not found in Neo4j")
                return {"success": False, "message": "Course not found"}
            print(f"✅ Course found: {course_check['code']} - {course_check['title']}")

            print("🔹 Checking if course already exists in playlist...")
            already_exists = s.run("""
                MATCH (u:User {username: $username})-[:HAS_PLAYLIST]->(p:Playlist)-[:CONTAINS]->(c:Course {course_code: $course_code})
                RETURN c
            """, username=username, course_code=course_code).single()

            if already_exists:
                print("⚠️ Course already exists in playlist")
                return {"success": False, "message": "Course already in playlist"}

            print("🔹 Creating/fetching playlist and linking course...")
            s.run("""
                MATCH (u:User {username: $username})
                MATCH (c:Course {course_code: $course_code})
                MERGE (p:Playlist {id: $playlist_id})
                  ON CREATE SET p.name = $playlist_name, p.created_at = datetime()
                MERGE (u)-[:HAS_PLAYLIST]->(p)
                MERGE (p)-[:CONTAINS]->(c)
            """, username=username, course_code=course_code,
                 playlist_id=playlist_id, playlist_name="My Playlist")

            print("✅ Course successfully added to playlist in Neo4j")

            return {
                "success": True,
                "message": f"Added {course_code} to playlist",
                "course_details": {
                    "code": course_check['code'],
                    "title": course_check['title'],
                    "credits": course_check['credits'],
                    "semester": course_check['semester']
                }
            }

    except Exception as e:
        print(f"❌ [ERROR] add_to_playlist: {e}")
        return {"success": False, "message": f"Error: {str(e)}"}

def remove_from_playlist(username, course_code):
    """Remove a course from user's playlist"""
    if not driver:
        return {"success": False, "message": "Database connection error"}

    try:
        with driver.session(database=NEO4J_DATABASE) as s:
            result = s.run("""
                MATCH (u:User {username: $username})-[:HAS_PLAYLIST]->(p:Playlist)-[r:CONTAINS]->(c:Course {course_code: $course_code})
                DELETE r
                RETURN c.course_code AS code
            """, username=username, course_code=course_code).single()

            if result:
                return {"success": True, "message": f"Removed {course_code} from playlist"}
            else:
                return {"success": False, "message": "Course not found in playlist"}
    except Exception as e:
        print(f"Error removing from playlist: {e}")
        return {"success": False, "message": f"Error: {str(e)}"}

def get_playlist_count(username):
    """Get count of courses in user's playlist"""
    if not driver:
        return 0
    try:
        with driver.session(database=NEO4J_DATABASE) as s:
            result = s.run("""
                MATCH (u:User {username: $username})-[:HAS_PLAYLIST]->(p:Playlist)-[:CONTAINS]->(c:Course)
                RETURN count(c) AS count
            """, username=username).single()
            return result['count'] if result else 0
    except Exception as e:
        print(f"Error getting playlist count: {e}")
        return 0

# ============================================================================
# COURSE PROPERTY EXTRACTION & FORMATTING
# ============================================================================

def extract_all_course_properties(course_dict: Dict) -> Dict:
    """Extract all course properties from Neo4j result with RIASEC data"""
    extracted = {}
    
    # Basic course info
    extracted['course_code'] = course_dict.get('course_code', 'N/A')
    extracted['course_title'] = course_dict.get('course_title') or course_dict.get('title', 'N/A')
    extracted['description'] = course_dict.get('description', 'No description available')
    extracted['credits'] = course_dict.get('credits', 'N/A')
    extracted['level'] = course_dict.get('level', 'Beginner')
    extracted['department'] = course_dict.get('department', 'N/A')
    extracted['semester'] = course_dict.get('recommended_semester') or course_dict.get('semester', 'Elective')
    extracted['category'] = course_dict.get('category', 'ELECTIVE')
    extracted['duration'] = course_dict.get('duration', 'N/A')
    extracted['instructor'] = course_dict.get('instructor', 'TBD')
    extracted['subject_area'] = course_dict.get('subject_area', 'N/A')
    extracted['prerequisites'] = course_dict.get('prerequisites') or course_dict.get('prereq_course_codes', 'None')
    
    # RIASEC alignment scores
    riasec_scores = {
        'R': course_dict.get('R', 0.0),
        'I': course_dict.get('I', 0.0),
        'A': course_dict.get('A', 0.0),
        'S': course_dict.get('S', 0.0),
        'E': course_dict.get('E', 0.0),
        'C': course_dict.get('C', 0.0)
    }
    extracted['riasec_alignment'] = riasec_scores
    
    # Course RIASEC vector
    if course_dict.get('course_riasec_vector'):
        vector = course_dict.get('course_riasec_vector', [])
        extracted['riasec_vector'] = {
            'R': vector[0] if len(vector) > 0 else 0,
            'I': vector[1] if len(vector) > 1 else 0,
            'A': vector[2] if len(vector) > 2 else 0,
            'S': vector[3] if len(vector) > 3 else 0,
            'E': vector[4] if len(vector) > 4 else 0,
            'C': vector[5] if len(vector) > 5 else 0
        }
    
    return extracted

def format_course_for_display(course_dict: Dict, detailed=False) -> str:
    """Format course data for human-readable display"""
    props = extract_all_course_properties(course_dict)
    
    if detailed:
        # Full detailed view
        lines = [
            f"📚 **{props['course_code']}: {props['course_title']}**",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"📝 **Description:** {props['description']}",
            f"📊 **Credits:** {props['credits']}",
            f"🎓 **Level:** {props['level']}",
            f"🏢 **Department:** {props['department']}",
            f"📅 **Semester:** {props['semester']}",
            f"🏷️  **Category:** {props['category']}",
            f"⏱️  **Duration:** {props['duration']}",
            f"👨‍🏫 **Instructor:** {props['instructor']}",
            f"📍 **Subject Area:** {props['subject_area']}",
            f"📋 **Prerequisites:** {props['prerequisites'] if props['prerequisites'] != 'None' else 'None - Foundation course'}",
        ]
        
        # Add RIASEC alignment
        riasec = props.get('riasec_alignment', {})
        if any(riasec.values()):
            lines.append("🎯 **Career Personality Alignment:**")
            trait_names = {'R': 'Realistic', 'I': 'Investigative', 'A': 'Artistic', 
                          'S': 'Social', 'E': 'Enterprising', 'C': 'Conventional'}
            for trait, score in riasec.items():
                if score > 0:
                    bar_length = int(score * 10)
                    bar = "█" * bar_length + "░" * (10 - bar_length)
                    lines.append(f"  {trait_names[trait]}: {bar} {score:.1%}")
        
        return "\n".join(lines)
    else:
        # Compact view for chat
        return f"**{props['course_code']}** - {props['course_title']} ({props['level']}, {props['credits']} credits, Sem {props['semester']})"

def format_courses_for_chat_response(courses, max_courses=5):
    """Format courses for chat display with all properties"""
    if not courses:
        return []
    
    formatted = []
    for course in courses[:max_courses]:
        props = extract_all_course_properties(course)
        formatted.append({
            'course_code': props['course_code'],
            'title': props['course_title'],
            'description': props['description'][:120] if props['description'] else '',
            'level': props['level'],
            'credits': props['credits'],
            'duration': props['duration'],
            'semester': props['semester'],
            'department': props['department'],
            'prerequisites': props['prerequisites'],
            'instructor': props['instructor'],
            'riasec_alignment': props.get('riasec_alignment', {}),
            'score': round(course.get('score', 0) * 100, 1) if course.get('score') else None
        })
    
    return formatted

# ============================================================================
# DEPENDENCY & PATHWAY FUNCTIONS
# ============================================================================

def get_course_dependencies(_drv, course_code: str, direction: str = "prerequisites") -> Dict[str, Any]:
    """Retrieve course dependency information"""
    if direction == "prerequisites":
        cypher = """
        MATCH (c:Course {course_code: $course_code})
        OPTIONAL MATCH prereq_path = (c)-[:REQUIRES*1..5]->(pre:Course)
        WITH c, collect(DISTINCT prereq_path) as paths
        RETURN c.course_code AS course_code,
               c.course_title AS title,
               c.prereq_course_codes AS prereq_codes,
               [path in paths WHERE path IS NOT NULL | [node in nodes(path) | {code: node.course_code, title: node.course_title}]] AS prerequisite_paths
        """
    else:
        cypher = """
        MATCH (c:Course {course_code: $course_code})
        OPTIONAL MATCH postreq_path = (c)<-[:REQUIRES*1..5]-(post:Course)
        WITH c, collect(DISTINCT postreq_path) as paths
        RETURN c.course_code AS course_code,
               c.course_title AS title,
               c.prereq_course_codes AS prereq_codes,
               [path in paths WHERE path IS NOT NULL | [node in nodes(path) | {code: node.course_code, title: node.course_title}]] AS postrequisite_paths
        """

    result = run_read_cypher(_drv, cypher, {'course_code': course_code})
    return result[0] if result else {}

def build_dependency_tree(_drv, course_code: str, direction: str = "prerequisites") -> Optional[str]:
    """Build ASCII dependency tree visualization"""
    deps = get_course_dependencies(_drv, course_code, direction)
    if not deps:
        return None

    paths_key = "prerequisite_paths" if direction == "prerequisites" else "postrequisite_paths"
    tree_paths = deps.get(paths_key, []) or []
    valid_paths = [path for path in tree_paths if path and len(path) > 1]

    if not valid_paths and direction == "postrequisites":
        search_query = """
        MATCH (c:Course)
        WHERE c.prereq_course_codes CONTAINS $course_code
        RETURN c.course_code AS course_code, c.course_title AS title
        LIMIT 200
        """
        dependent_courses = run_read_cypher(_drv, search_query, {"course_code": course_code}) or []

        if dependent_courses:
            course_title = deps.get("title", "")
            header = f"{course_code} - {course_title or '[Title not available]'}"
            lines = [f"📚 {header}", f"{'─' * (len(header) + 4)}", "Courses This Unlocks:"]

            for i, dep_course in enumerate(dependent_courses):
                dep_code = dep_course.get("course_code", "")
                dep_title = dep_course.get("title", "")
                display = f"{dep_code} - {dep_title or '[Title not available]'}"
                connector = "    " if i == 0 else "or  "
                lines.append(f"{connector}{display}")

            return "\n".join(lines)

    if not valid_paths and direction == "prerequisites":
        raw_prereqs = deps.get("prereq_codes") or deps.get("prereq_course_codes") or ""
        codes = [c.strip() for c in re.split(r'[,;\n]+', raw_prereqs) if c.strip()]
        if not codes:
            return None

        cypher_titles = """
        UNWIND $codes AS code
        OPTIONAL MATCH (x:Course {course_code: code})
        RETURN code AS code, x.course_title AS title
        """
        rows = run_read_cypher(_drv, cypher_titles, {"codes": codes}) or []
        titles_map = {r.get("code"): r.get("title") or "" for r in rows}

        course_title = deps.get("title", "")
        header = f"{course_code} - {course_title or '[Title not available]'}"
        lines = [f"📚 {header}", f"{'─' * (len(header) + 4)}", "Prerequisites:"]

        for i, code in enumerate(codes):
            title = titles_map.get(code, "")
            display = f"{code} - {title or '[Title not available]'}"
            connector = "    " if i == 0 else "or  "
            lines.append(f"{connector}{display}")

        return "\n".join(lines)

    if not valid_paths:
        return None

    tree = {}
    for path in valid_paths:
        current = tree
        for node in path[1:]:
            code = node.get("code", "")
            title = node.get("title", "")
            display = f"{code} - {title or '[Title not available]'}"
            current = current.setdefault(display, {})

    direction_label = "Prerequisites" if direction == "prerequisites" else "Courses This Unlocks"
    course_title = deps.get("title", "")
    header = f"{course_code} - {course_title or '[Title not available]'}"
    lines = [f"📚 {header}", f"{'─' * (len(header) + 4)}", direction_label + ":"]

    def render_tree(subtree, prefix=""):
        items = list(subtree.items())
        for i, (display_name, children) in enumerate(items):
            connector = "    " if i == 0 else "or  "
            lines.append(f"{prefix}{connector}{display_name}")
            if children:
                render_tree(children, prefix + "    ")

    render_tree(tree)
    return "\n".join(lines)

def build_full_pathway_tree(_drv, course_code: str) -> Optional[str]:
    """Build comprehensive ASCII tree showing prerequisites AND postrequisites"""
    prereq_deps = get_course_dependencies(_drv, course_code, "prerequisites")
    postreq_deps = get_course_dependencies(_drv, course_code, "postrequisites")

    if not prereq_deps and not postreq_deps:
        return None

    course_title = prereq_deps.get("title", "") or postreq_deps.get("title", "")
    lines = [
        "=" * 80,
        f"🎓 COMPLETE LEARNING PATHWAY FOR: {course_code} - {course_title or '[Title not available]'}",
        "=" * 80,
        ""
    ]

    lines.append("📚 PREREQUISITES (What to study BEFORE):")
    lines.append("─" * 80)

    prereq_paths = prereq_deps.get("prerequisite_paths", []) or []
    valid_prereq_paths = [path for path in prereq_paths if path and len(path) > 1]

    def render_tree(subtree, prefix=""):
        items = list(subtree.items())
        for i, (display_name, children) in enumerate(items):
            connector = "    " if i == 0 else "or  "
            lines.append(f"{prefix}{connector}{display_name}")
            if children:
                render_tree(children, prefix + "    ")

    if valid_prereq_paths:
        prereq_tree = {}
        for path in valid_prereq_paths:
            current = prereq_tree
            for node in path[1:]:
                code = node.get("code", "")
                title = node.get("title", "")
                display = f"{code} - {title or '[Title not available]'}"
                current = current.setdefault(display, {})
        render_tree(prereq_tree)
    else:
        raw_prereqs = prereq_deps.get("prereq_codes") or prereq_deps.get("prereq_course_codes") or ""
        codes = [c.strip() for c in re.split(r'[,;\n]+', raw_prereqs) if c.strip()]
        if codes:
            cypher_titles = """
            UNWIND $codes AS code
            OPTIONAL MATCH (x:Course {course_code: code})
            RETURN code AS code, x.course_title AS title
            """
            rows = run_read_cypher(_drv, cypher_titles, {"codes": codes}) or []
            title_map = {r.get("code"): r.get("title") or "" for r in rows}
            for i, code in enumerate(codes):
                title = title_map.get(code, "")
                connector = "    " if i == 0 else "or  "
                lines.append(f"{connector}{code} - {title or '[Title not available]'}")
        else:
            lines.append("   ℹ️  No prerequisites found - this might be a foundational course!")
    lines.append("")

    lines.append("🎯 YOUR PREFERRED COURSE:")
    lines.append("─" * 80)
    lines.append(f"   ➤  {course_code} - {course_title or '[Title not available]'}")
    lines.append("")

    lines.append("🚀 POSTREQUISITES (What you can study AFTER):")
    lines.append("─" * 80)

    postreq_paths = postreq_deps.get("postrequisite_paths", []) or []
    valid_postreq_paths = [path for path in postreq_paths if path and len(path) > 1]

    if valid_postreq_paths:
        postreq_tree = {}
        for path in valid_postreq_paths:
            current = postreq_tree
            for node in path[1:]:
                code = node.get("code", "")
                title = node.get("title", "")
                display = f"{code} - {title or '[Title not available]'}"
                current = current.setdefault(display, {})
        render_tree(postreq_tree)
    else:
        search_query = """
        MATCH (c:Course)
        WHERE c.prereq_course_codes CONTAINS $course_code
        RETURN c.course_code AS course_code, c.course_title AS title
        LIMIT 50
        """
        dependent_courses = run_read_cypher(_drv, search_query, {"course_code": course_code}) or []
        if dependent_courses:
            for i, dep in enumerate(dependent_courses):
                code = dep.get("course_code", "")
                title = dep.get("title", "")
                connector = "    " if i == 0 else "or  "
                lines.append(f"{connector}{code} - {title or '[Title not available]'}")
        else:
            lines.append("   ℹ️  No advanced courses found - this might be a terminal/capstone course!")
    lines.append("")
    lines.append("=" * 80)
    lines.append("💡 TIP: Follow this pathway from top to bottom for optimal learning progression!")
    lines.append("=" * 80)

    return "\n".join(lines)

# ============================================================================
# CAREER PLANNING FUNCTIONS
# ============================================================================

def get_career_recommendations(username, _drv, database_name: str = None) -> Dict[str, Any]:
    """Get career recommendations based on RIASEC results and marks"""
    if not driver:
        return {}
    
    try:
        with driver.session(database=database_name or NEO4J_DATABASE) as s:
            # Get user's RIASEC results and marks
            result = s.run("""
                MATCH (u:User {username: $username})
                RETURN u.riasec_top3 AS top3,
                       u.riasec_scores AS scores
            """, username=username).single()
            
            if not result or not result['top3']:
                return {}
            
            top3 = result['top3']
            
            # Get recommended courses based on RIASEC
            cypher = """
            MATCH (c:Course)
            WHERE (c.R IN $top3 OR c.I IN $top3 OR c.A IN $top3 OR 
                   c.S IN $top3 OR c.E IN $top3 OR c.C IN $top3)
            RETURN c.course_code AS code,
                   c.course_title AS title,
                   c.recommended_semester AS semester,
                   c.description AS description
            LIMIT 10
            """
            
            courses = s.run(cypher, top3=top3)
            
            return {
                'top_traits': top3,
                'recommended_courses': [dict(record) for record in courses]
            }
    except Exception as e:
        print(f"Error getting career recommendations: {e}")
        return {}

def get_semester_courses(username, semester, _drv, database_name: str = None) -> List[Dict]:
    """Get all courses for a specific semester for a user"""
    if not driver:
        return []
    
    try:
        with driver.session(database=database_name or NEO4J_DATABASE) as s:
            result = s.run("""
                MATCH (u:User {username: $username})-[:HAS_PLAYLIST]->(p:Playlist)-[:CONTAINS]->(c:Course)
                WHERE c.recommended_semester = $semester OR c.recommended_semester CONTAINS $sem_str
                RETURN c.course_code AS course_code,
                       c.course_title AS course_title,
                       c.credits AS credits,
                       c.description AS description,
                       c.R AS R, c.I AS I, c.A AS A, c.S AS S, c.E AS E, c.C AS C
                ORDER BY c.course_code
            """, username=username, semester=int(semester), sem_str=str(semester))
            
            return [dict(record) for record in result]
    except Exception as e:
        print(f"Error getting semester courses: {e}")
        return []

# ============================================================================
# SEMANTIC SEARCH FUNCTIONS
# ============================================================================

def semantic_search_courses(_drv, query_text: str, top_k: int = 10) -> List[Dict[str, Any]]:
    if not embedding_model:
        q = """
        MATCH (c:Course)
        WHERE toLower(c.course_title) CONTAINS toLower($q) OR toLower(c.course_code) CONTAINS toLower($q)
        RETURN c.course_code AS course_code, 
               c.course_title AS course_title, 
               c.subject_area AS subject_area,
               c.credits AS credits,
               c.level AS level,
               c.department AS department,
               c.description AS description,
               c.prereq_course_codes AS prereq_course_codes,
               c.R AS R, c.I AS I, c.A AS A, c.S AS S, c.E AS E, c.C AS C,
               c.course_riasec_vector AS course_riasec_vector,
               c.recommended_semester AS recommended_semester,
               c.category AS category,
               0.5 as score
        LIMIT $top_k
        """
        return run_read_cypher(_drv, q, {"q": query_text, "top_k": top_k})

    query_vector = embedding_model.encode(query_text, convert_to_numpy=True)

    cypher = """
    CALL db.index.vector.queryNodes('course_embedding_index', $top_k, $query_vector) 
    YIELD node, score
    MATCH (c:Course) WHERE elementId(c) = elementId(node)
    RETURN c.course_code AS course_code,
           c.course_title AS course_title,
           c.subject_area AS subject_area,
           c.credits AS credits,
           c.level AS level,
           c.department AS department,
           c.description AS description,
           c.prereq_course_codes AS prereq_course_codes,
           c.R AS R, c.I AS I, c.A AS A, c.S AS S, c.E AS E, c.C AS C,
           c.course_riasec_vector AS course_riasec_vector,
           c.recommended_semester AS recommended_semester,
           c.category AS category,
           score
    ORDER BY score DESC
    """

    try:
        return run_read_cypher(_drv, cypher, {
            'query_vector': query_vector.tolist(),
            'top_k': top_k
        })
    except Exception as e:
        print(f"Semantic search error: {e}")
        return []

def semantic_search_jobs(_drv, query_text: str, top_k: int = 10) -> List[Dict[str, Any]]:
    if not embedding_model:
        return []

    query_vector = embedding_model.encode(query_text, convert_to_numpy=True)

    cypher = """
    CALL db.index.vector.queryNodes('job_embedding_index', $top_k, $query_vector) 
    YIELD node, score
    MATCH (j:Job) WHERE elementId(j) = elementId(node)
    OPTIONAL MATCH (c:Course)-[:MATCHES_JOB]->(j)
    RETURN j.job_id AS job_id,
           j.job_title AS job_title,
           j.ss_jd AS skills_description,
           score,
           collect(DISTINCT c.course_code) AS related_courses
    ORDER BY score DESC
    """

    try:
        return run_read_cypher(_drv, cypher, {
            'query_vector': query_vector.tolist(),
            'top_k': top_k
        })
    except Exception as e:
        print(f"Job search error: {e}")
        return []

# ============================================================================
# CONVERSATION DETECTION
# ============================================================================

def detect_casual_conversation(user_input: str) -> bool:
    input_lower = user_input.lower().strip()

    casual_patterns = [
        r'^(hi|hello|hey+|hii+|sup|what\'s up)$',
        r'^good (morning|afternoon|evening)$',
        r'^(ok|okay|yes|no|yep|nope|sure|thanks|thank you)$',
        r'^(who are you|what are you|what can you do)$',
        r'^.{1,2}$',
        r'^(.)\1{2,}$',
    ]

    for pattern in casual_patterns:
        if re.match(pattern, input_lower):
            return True

    if len(input_lower) < 4:
        course_keywords = ['course', 'class', 'job', 'career', 'study', 'learn', 'degree']
        if not any(keyword in input_lower for keyword in course_keywords):
            return True

    return False

def get_conversational_response(user_input: str, username: str = None) -> str:
    input_lower = user_input.lower().strip()
    greeting = f"Hi there" if not username else f"Hi {username}"

    if re.match(r'^(hi|hello|hey+|hii+)$', input_lower):
        return f"""{greeting}!

I'm your Jain University Course & Career Assistant. I'm here to help you explore:

- Courses - Find courses that match your interests
- Prerequisites - Discover what you need to study before advanced courses  
- Career Paths - Explore job opportunities for Jain University graduates
- Learning Pathways - Plan your academic journey
- Your Playlist - View and manage your selected courses

What would you like to know about? You can ask me things like:
- "What courses are available in Computer Science?"
- "What are the prerequisites for Data Science?"
- "What jobs can I get with an AI degree?"
- "Show me my playlist for semester 3"

How can I help you today?"""

    elif re.match(r'^(what\'s up|sup)$', input_lower):
        return f"""Not much {username or 'there'}! Just here waiting to help Jain University students like you navigate their academic journey!

I can help you discover courses, understand prerequisites, explore career opportunities, and plan your learning pathway.

What's on your mind? Looking for a specific course or career advice?"""

    else:
        return """I'm not sure what you meant by that, but I'm here to help!

I specialize in helping Jain University students with:
- Course recommendations and information
- Understanding prerequisites and dependencies
- Career guidance and job opportunities  
- Academic pathway planning

Try asking me something like "What courses are good for AI?" or "Show me computer science prerequisites" and I'll give you detailed, helpful information!

What would you like to know about?"""

# ============================================================================
# QUERY PROCESSING
# ============================================================================

def process_user_query(_drv, user_input: str, username: str = None) -> Dict[str, Any]:
    """Process user query and determine appropriate search strategy"""

    if detect_casual_conversation(user_input):
        return {
            'courses': [],
            'jobs': [],
            'ascii_tree': None,
            'search_type': 'casual_conversation',
            'context': 'jain_university',
            'specific_course': None,
            'conversational_response': get_conversational_response(user_input, username)
        }

    input_lower = user_input.lower()
    results = {
        'courses': [],
        'jobs': [],
        'ascii_tree': None,
        'search_type': 'general',
        'context': 'jain_university',
        'specific_course': None
    }

    course_codes = re.findall(r'([A-Za-z]{2,}[-\s]?\d{2,3})', user_input, re.IGNORECASE)

    course_results = semantic_search_courses(_drv, user_input, top_k=10)
    results['courses'] = course_results

    job_terms = [
        "job", "career", "work", "employment", "opportunity", "hire", "hiring",
        "profession", "industry", "vacancy", "recruitment"
    ]

    prereq_terms = [
        "prerequisite", "prereq", "pre-req", "dependency", "requirement",
        "required before", "before taking", "needed before", "need to learn before",
        "must complete before", "foundation for", "prepare for", "pre req", "pre reqs", "pre recs"
    ]

    postreq_terms = [
        "postrequisite", "postreq", "post-req", "leads to", "next", "after",
        "can take after", "follow-up", "advanced course", "what comes after",
        "continue with", "next step", "progress to", "post rec", "post recs", "post req", "post reqs"
    ]

    pathway_terms = [
        "pathway", "learning path", "study path", "progression", "roadmap",
        "journey", "complete path", "full path", "learning journey", "entire path",
        "curriculum map", "flow", "syllabus flow", "track", "academic track"
    ]

    def contains_any(text: str, terms: list) -> bool:
        return any(term in text for term in terms)

    is_job_query = contains_any(input_lower, job_terms)
    is_prereq_query = contains_any(input_lower, prereq_terms)
    is_postreq_query = contains_any(input_lower, postreq_terms)
    is_pathway_query = contains_any(input_lower, pathway_terms)

    if is_pathway_query:
        results['search_type'] = 'full_pathway'

        if course_codes:
            main_course = course_codes[0].upper().replace(' ', '-')
            results['ascii_tree'] = build_full_pathway_tree(_drv, main_course)
            results['specific_course'] = main_course
        elif course_results:
            main_course = course_results[0]['course_code']
            results['ascii_tree'] = build_full_pathway_tree(_drv, main_course)
            results['specific_course'] = main_course

    elif course_codes and (is_prereq_query or is_postreq_query):
        main_course = course_codes[0].upper().replace(' ', '-')
        direction = "prerequisites" if is_prereq_query else "postrequisites"
        results['ascii_tree'] = build_dependency_tree(_drv, main_course, direction)
        results['search_type'] = f'dependency_{direction}'
        results['specific_course'] = main_course

    elif is_job_query:
        job_results = semantic_search_jobs(_drv, user_input, top_k=8)
        results['jobs'] = job_results
        results['search_type'] = 'job_search'

    else:
        results['search_type'] = 'course_search'

        if (is_prereq_query or is_postreq_query) and course_results:
            main_course = course_results[0]['course_code']
            direction = "prerequisites" if is_prereq_query else "postrequisites"
            results['ascii_tree'] = build_dependency_tree(_drv, main_course, direction)
            results['specific_course'] = main_course

        elif course_results:
            main_course = course_results[0]['course_code']
            results['ascii_tree'] = build_dependency_tree(_drv, main_course, "prerequisites")

    return results

def format_course_bolding(text):
    """Automatically bolds course codes and titles"""
    pattern = r"\b([A-Z]{2,4}-\d{2,3})[:\-]\s*([A-Za-z& ]+)"

    def repl(match):
        code = match.group(1).strip()
        title = match.group(2).strip()
        return f"**{code}: {title}**"

    return re.sub(pattern, repl, text)

# ============================================================================
# RESPONSE GENERATION
# ============================================================================

def generate_response(query_results: Dict[str, Any], user_input: str, client,
                      conversation_history: List[Dict] = None,
                      reference_document: str = None,
                      _drv=None,
                      database_name: str = None,
                      username: str = None) -> str:
    
    if query_results.get("search_type") == "casual_conversation":
        return query_results.get("conversational_response",
                                 "Hello! How can I help you with Jain University courses today?")

    if query_results.get("search_type", "").startswith("dependency_prerequisites"):
        top = None
        if query_results.get("courses"):
            top = query_results["courses"][0]
        if top and top.get("course_code"):
            return f"I found this course matching your query: {top.get('course_code')} - {top.get('course_title', '')}. Prerequisite information is being processed."
        return "I couldn't find prerequisites for that course in the database."

    if not client:
        return generate_fallback_response(query_results, user_input)

    memory = SlidingWindowMemory(recent_messages_count=6, max_context_tokens=1500)

    context = ""
    if conversation_history:
        context = memory.build_context(conversation_history, user_input, client, username)

    # Format courses with ALL properties
    courses_info = ""
    if query_results.get('courses'):
        courses_info = "AVAILABLE COURSES:\n"
        for course in query_results['courses'][:5]:
            formatted = format_course_for_display(course, detailed=False)
            courses_info += f"• {formatted}\n"

    jobs_info = ""
    if query_results.get('jobs'):
        jobs_info = "CAREER OPPORTUNITIES:\n"
        for job in query_results['jobs'][:3]:
            job_title = job.get('job_title', '')
            related_courses = job.get('related_courses', [])
            jobs_info += f"- {job_title}"
            if related_courses:
                jobs_info += f" (requires: {', '.join(related_courses[:2])})"
            jobs_info += "\n"

    formatted_top_k = "Not available"
    if username and _drv:
        try:
            with _drv.session(database=database_name or NEO4J_DATABASE) as s:
                result = s.run("""
                    MATCH (u:User {username: $username})
                    RETURN u.riasec_scores AS all_scores
                """, username=username).single()

                if result and result['all_scores']:
                    riasec_scores = json.loads(result['all_scores'])
                    top_k = sorted(riasec_scores.items(), key=lambda x: x[1], reverse=True)[:3]
                    formatted_top_k = ", ".join([f"{trait}: {score * 100:.1f}%" for trait, score in top_k])
        except Exception as e:
            print(f"Error fetching RIASEC scores: {e}")
            formatted_top_k = "Not available"

    system_prompt = f"""You are an academic counselor for Jain University who is genuinely curious about students' interests and goals.

INSTRUCTIONS:
1. Use the provided context for personal information (user's name is in context)
2. Reference conversation history for context about past topics
3. Use recent messages for immediate conversation flow
4. Only mention information that's explicitly in these sections
5. If asked about something not in context, say "We haven't discussed that yet"
6. Always personalize responses using the student's name when available

CURIOSITY & ENGAGEMENT:
- ALWAYS end your response with 1-2 curious questions
- Ask about their interests, preferences, or experiences related to the topic
- Address students by their name when you know it

RIASEC SCORES & CAREER FIT:
- Student's top 3 personality traits: {formatted_top_k}
- Use these to suggest aligned courses/careers when relevant

Keep responses 2-3 paragraphs, recommend relevant courses with full details, then ask engaging questions."""

    full_context = []
    if context:
        full_context.append(context)

    current_query_section = f"CURRENT QUERY: {user_input}"
    if courses_info:
        current_query_section += f"\n\n{courses_info}"
    if jobs_info:
        current_query_section += f"\n\n{jobs_info}"

    full_context.append(current_query_section)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "\n\n".join(full_context)}
    ]

    try:
        response = mistral_request(
            client=client,
            model=MISTRAL_MODEL,
            messages=messages,
            max_tokens=400,
            temperature=0.3
        )

        response = format_course_bolding(response)

        if not any(response.rstrip().endswith(q) for q in ['?', '? ', '?)']):
            response += " What aspects of this interest you most?"

        return response

    except Exception as e:
        fallback = generate_fallback_response(query_results, user_input)
        return format_course_bolding(fallback)

def generate_fallback_response(query_results: Dict[str, Any], user_input: str) -> str:
    courses_count = len(query_results.get('courses', []))
    jobs_count = len(query_results.get('jobs', []))

    if courses_count == 0 and jobs_count == 0:
        return "I couldn't find specific information about that in our Jain University database. Could you rephrase your question or try asking about a different course or career area?"

    response_parts = []

    if courses_count > 0:
        response_parts.append("I found these relevant courses at Jain University:")
        for course in query_results['courses'][:3]:
            formatted = format_course_for_display(course, detailed=False)
            response_parts.append(f"• {formatted}")

    if jobs_count > 0:
        response_parts.append("\nRelated career opportunities:")
        for job in query_results['jobs'][:3]:
            job_title = job.get('job_title', '')
            response_parts.append(f"• {job_title}")

    return "\n".join(response_parts)