"""
Jain University Course & Career Advisor - Core Functions Module
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

# Database Helper Functions
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

def save_marks(username, subject, marks_scored, total_marks):
    """Save marks to Neo4j"""
    if not driver:
        return False
    try:
        # Check if subject already exists for this user
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

# RIASEC Functions
def save_riasec_results(username, answers, riasec_results):
    """Save complete RIASEC results to Neo4j without riasec_top3_scores"""
    if not driver:
        return False
    
    try:
        with driver.session(database=NEO4J_DATABASE) as s:
            # Save all RIASEC data (without top3_scores)
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
    """Get complete RIASEC results from Neo4j - handles missing properties gracefully"""
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
                # Handle potential missing properties gracefully
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
    
    # Define RIASEC questions here so it's available in this module
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
    
    # Count responses per trait
    trait_responses = {'R': [], 'I': [], 'A': [], 'S': [], 'E': [], 'C': []}
    
    for question, trait in RIASEC_QUESTIONS:
        response = answers.get(question, 0)
        trait_responses[trait].append(response)
    
    # Calculate average score for each trait
    scores = {}
    for trait, responses in trait_responses.items():
        if responses:
            scores[trait] = sum(responses) / len(responses)
        else:
            scores[trait] = 0.0
    
    # Normalize scores to sum to 1
    total = sum(scores.values())
    if total > 0:
        for trait in scores:
            scores[trait] = scores[trait] / total
    
    # Get top 3 traits
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

# Memory Management System
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

            # Extract name
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

            # Extract interests with confidence
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

            # Extract course codes
            course_codes = re.findall(r'\b([A-Z]{2,4}[-\s]?\d{2,3})\b', content)
            for code in course_codes:
                profile['mentioned_courses'].add(code.upper().replace(' ', '-'))

        return profile

    def build_context(self, messages: List[Dict], current_query: str, client=None) -> str:
        memory = self.initialize_memory()
        profile = self.extract_user_profile(messages)

        context_parts = []
        user_message_count = sum(1 for msg in messages if msg['role'] == 'user' and not msg.get('is_code'))

        # Session status
        if user_message_count <= 1:
            context_parts.append("SESSION: First message")
        else:
            context_parts.append(f"SESSION: {user_message_count} messages so far")

        # Student profile
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

        # Handle conversation history
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

# Semantic Search Functions
def semantic_search_courses(_drv, query_text: str, top_k: int = 10) -> List[Dict[str, Any]]:
    if not embedding_model:
        # Fallback: simple text search
        q = """
        MATCH (c:Course)
        WHERE toLower(c.course_title) CONTAINS toLower($q) OR toLower(c.course_code) CONTAINS toLower($q)
        RETURN c.course_code AS course_code, 
               c.course_title AS title, 
               c.subject_area AS subject_area,
               c.prereq_course_codes AS prereq_codes,
               0.5 as score
        LIMIT $top_k
        """
        return run_read_cypher(_drv, q, {"q": query_text, "top_k": top_k})

    query_vector = embedding_model.encode(query_text, convert_to_numpy=True)

    cypher = """
    CALL db.index.vector.queryNodes('course_embedding_index', $top_k, $query_vector) 
    YIELD node, score
    MATCH (c:Course) WHERE id(c) = id(node)
    OPTIONAL MATCH (c)-[:REQUIRES]->(pre:Course)
    OPTIONAL MATCH (post:Course)-[:REQUIRES]->(c)
    OPTIONAL MATCH (c)-[:BELONGS_TO]->(s:SubjectArea)
    OPTIONAL MATCH (c)-[:MATCHES_JOB]->(j:Job)
    RETURN c.course_code AS course_code,
           c.course_title AS title,
           c.subject_area AS subject_area,
           c.prereq_course_codes AS prereq_codes,
           score,
           collect(DISTINCT pre.course_code) AS direct_prerequisites,
           collect(DISTINCT post.course_code) AS postrequisites,
           collect(DISTINCT s.name) AS subject_areas,
           collect(DISTINCT j.job_title) AS job_matches
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
    MATCH (j:Job) WHERE id(j) = id(node)
    OPTIONAL MATCH (c:Course)-[:MATCHES_JOB]->(j)
    OPTIONAL MATCH (s:SubjectArea)-[:MATCHES_JOB]->(j)
    RETURN j.job_id AS job_id,
           j.job_title AS job_title,
           j.ss_jd AS skills_description,
           score,
           collect(DISTINCT c.course_code) AS related_courses,
           collect(DISTINCT c.course_title) AS course_titles,
           collect(DISTINCT s.name) AS related_subjects
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

# Conversation detection
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

def get_conversational_response(user_input: str) -> str:
    input_lower = user_input.lower().strip()

    if re.match(r'^(hi|hello|hey+|hii+)$', input_lower):
        return """Hi there! 

I'm your Jain University Course & Career Assistant. I'm here to help you explore:

- Courses - Find courses that match your interests
- Prerequisites - Discover what you need to study before advanced courses  
- Career Paths - Explore job opportunities for Jain University graduates
- Learning Pathways - Plan your academic journey

What would you like to know about? You can ask me things like:
- "What courses are available in Computer Science?"
- "What are the prerequisites for Data Science?"
- "What jobs can I get with an AI degree?"

How can I help you today?"""

    elif re.match(r'^(what\'s up|sup)$', input_lower):
        return """Not much! Just here waiting to help Jain University students like you navigate their academic journey!

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

# Query processing
def process_user_query(_drv, user_input: str) -> Dict[str, Any]:
    if detect_casual_conversation(user_input):
        return {
            'courses': [],
            'jobs': [],
            'ascii_tree': None,
            'search_type': 'casual_conversation',
            'context': 'jain_university',
            'specific_course': None,
            'conversational_response': get_conversational_response(user_input)
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

    # Check for specific course codes
    course_codes = re.findall(r'([A-Za-z]{2,}[-\s]?\d{2,3})', user_input, re.IGNORECASE)

    # Do semantic search for courses
    course_results = semantic_search_courses(_drv, user_input, top_k=10)
    results['courses'] = course_results

    # Check query intent
    is_job_query = any(term in input_lower for term in ['job', 'career', 'work', 'employment', 'opportunity', 'hire'])
    is_prereq_query = any(term in input_lower for term in ['prerequisite', 'prereq', 'pre-req', 'dependency', 'require', 'before'])

    if is_job_query:
        job_results = semantic_search_jobs(_drv, user_input, top_k=8)
        results['jobs'] = job_results
        results['search_type'] = 'job_search'
    elif is_prereq_query and course_results:
        main_course = course_results[0]['course_code']
        results['search_type'] = 'dependency_prerequisites'
        results['specific_course'] = main_course
    else:
        results['search_type'] = 'course_search'

    return results

# Response generation
def generate_response(query_results: Dict[str, Any], user_input: str, client,
                      conversation_history: List[Dict] = None,
                      reference_document: str = None,
                      _drv=None,
                      database_name: str = None,
                      username: str = None) -> str:

    # Handle casual conversation
    if query_results.get("search_type") == "casual_conversation":
        return query_results.get("conversational_response",
                                 "Hello! How can I help you with Jain University courses today?")

    # Handle prerequisite queries
    if query_results.get("search_type", "").startswith("dependency_prerequisites"):
        top = None
        if query_results.get("courses"):
            top = query_results["courses"][0]
        if top and top.get("course_code"):
            return f"I found this course matching your query: {top.get('course_code')} - {top.get('title', '')}. However, prerequisite information is not available in the database yet."
        return "I couldn't find prerequisites for that course in the database."

    if not client:
        return generate_fallback_response(query_results, user_input)

    # Use sliding window memory
    memory = SlidingWindowMemory(recent_messages_count=6, max_context_tokens=1500)

    # Build context
    context = ""
    if conversation_history:
        context = memory.build_context(conversation_history, user_input, client)

    # Prepare course/job info
    courses_info = ""
    jobs_info = ""

    if query_results.get('courses'):
        courses_info = "AVAILABLE COURSES:\n"
        for course in query_results['courses'][:5]:
            course_code = course.get('course_code', '')
            title = course.get('title') or course.get('course_title', '')
            subject = course.get('subject_area', '')
            courses_info += f"- {course_code}: {title} ({subject})\n"

    if query_results.get('jobs'):
        jobs_info = "CAREER OPPORTUNITIES:\n"
        for job in query_results['jobs'][:3]:
            job_title = job.get('job_title', '')
            related_courses = job.get('related_courses', [])
            jobs_info += f"- {job_title}"
            if related_courses:
                jobs_info += f" (requires: {', '.join(related_courses[:2])})"
            jobs_info += "\n"

    # System prompt
    system_prompt = """You are an academic counselor for Jain University who is genuinely curious about students' interests and goals.

INSTRUCTIONS:
1. Use the provided context for personal information
2. Reference conversation history for context about past topics
3. Use recent messages for immediate conversation flow
4. Only mention information that's explicitly in these sections
5. If asked about something not in context, say "We haven't discussed that yet"

CURIOSITY & ENGAGEMENT:
- ALWAYS end your response with 1-2 curious questions
- Ask about their interests, preferences, or experiences related to the topic

Keep responses 2-3 paragraphs, recommend relevant courses, then ask engaging questions."""

    # Build message for LLM
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

        # Ensure response ends with a question
        response = response.strip()
        if response and not any(response.rstrip().endswith(q) for q in ['?', '? ', '?)']):
            response += " What aspects of this interest you most?"

        return response

    except Exception as e:
        print(f"LLM Error: {str(e)}")
        return generate_fallback_response(query_results, user_input)

def generate_fallback_response(query_results: Dict[str, Any], user_input: str) -> str:
    courses_count = len(query_results.get('courses', []))
    jobs_count = len(query_results.get('jobs', []))

    if courses_count == 0 and jobs_count == 0:
        return "I couldn't find specific information about that in our Jain University database. Could you rephrase your question or try asking about a different course or career area?"

    response_parts = []

    if courses_count > 0:
        response_parts.append("I found these relevant courses at Jain University:")
        for course in query_results['courses'][:3]:
            course_code = course.get('course_code', '')
            title = course.get('title') or course.get('course_title', '')
            response_parts.append(f"• {course_code} - {title}")

    if jobs_count > 0:
        response_parts.append("\nRelated career opportunities:")
        for job in query_results['jobs'][:3]:
            job_title = job.get('job_title', '')
            response_parts.append(f"• {job_title}")

    return "\n".join(response_parts)