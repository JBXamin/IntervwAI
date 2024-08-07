import json
import os
import google.generativeai as genai
from flask import Flask, render_template, request, jsonify, url_for, redirect
from flask_cors import CORS
from google.auth.exceptions import DefaultCredentialsError
from uuid import uuid4

app = Flask(__name__)
CORS(app)

# Set the path to the credentials.json file
SERVICE_ACCOUNT_FILE = 'credentials.json'

# Check if the credentials file exists
if not os.path.isfile(SERVICE_ACCOUNT_FILE):
    print(f"Error: The file {SERVICE_ACCOUNT_FILE} does not exist.")
else:
    try:
        with open(SERVICE_ACCOUNT_FILE) as f:
            credentials = json.load(f)
        # Set the environment variable for Google Application Default Credentials
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = SERVICE_ACCOUNT_FILE
    except json.JSONDecodeError as e:
        print(f"Error: File {SERVICE_ACCOUNT_FILE} is not a valid JSON file. Details: {e}")
        credentials = None

# Check if credentials are loaded successfully
try:
    if credentials:
        genai.api_key = "AIzaSyDcw5qJwF3KkDNZI2cG_9vVvCDjLLMXGik"
except DefaultCredentialsError as e:
    print(f"Error: {e}")

qsns = 0
conversation_history = []
responses = []
generated_questions = []

interview_results = {}

INITIAL_PROMPT = "You are the interviewer in an interview. Ask me questions one by one."

def generate_response(query, initial_prompt=INITIAL_PROMPT):
    global conversation_history
    model = genai.GenerativeModel('gemini-1.5-flash-latest')

    current_conversation = "\n".join(conversation_history[-2:] + [f"user: {query}"])
    full_prompt = f"{initial_prompt}\n{current_conversation}"
    response = model.generate_content(full_prompt)

    text_content = response.candidates[0].content.parts[0].text
    conversation_history.append(f"ai: {text_content}")

    return text_content

def evaluate_answer(question, answer):
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    prompt = (f"Question: {question}\nAnswer: {answer}\nEvaluate the above answer as an interview response. Provide a "
              f"rating (Excellent, Good, Average, Poor) and explain why.")
    evaluation = model.generate_content(prompt)

    evaluation_text = evaluation.candidates[0].content.parts[0].text
    rating = "Average"
    if "Excellent" in evaluation_text:
        rating = "Excellent"
    elif "Good" in evaluation_text:
        rating = "Good"
    elif "Poor" in evaluation_text:
        rating = "Poor"

    return rating, evaluation_text

@app.route('/api/gemini', methods=['POST'])
def gemini():
    global qsns, responses, conversation_history, generated_questions
    data = request.json
    user_message = data.get('message', '')

    if not user_message:
        return jsonify({'response': 'No message provided'}), 400

    try:
        if qsns < len(generated_questions):
            current_question = generated_questions[qsns]
        else:
            current_question = generate_response(user_message)
            generated_questions.append(current_question)

        conversation_history.append(f"ai: {current_question}")
        ai_response = generate_response(user_message)
        conversation_history.append(f"user: {user_message}")
        rating, evaluation_text = evaluate_answer(current_question, user_message)
        response_entry = {
            'question': current_question,
            'answer': user_message,
            'rating': rating,
            'evaluation': evaluation_text
        }
        responses.append(response_entry)

        qsns += 1
        if qsns >= 5:  # Assuming we want to ask 5 questions
            session_id = str(uuid4())
            interview_results[session_id] = responses.copy()
            qsns = 0
            conversation_history.clear()
            responses.clear()
            generated_questions.clear()
            redirect_url = url_for('result', session_id=session_id)

            return jsonify({
                'response': ai_response,
                'redirect': redirect_url
            })

        conversation_history = conversation_history[-1:]

        return jsonify({'response': current_question})
    except Exception as e:
        return jsonify({'response': f'Error: {str(e)}'}), 500

@app.route('/')
def home():
    global qsns
    qsns=0
    conversation_history.clear()
    responses.clear()
    generated_questions.clear()
    interview_results.clear()
    return render_template('home.html')

@app.route('/login')
def login():
    return render_template('signin.html')

@app.route('/register')
def signup():
    return render_template('signup.html')

@app.route('/chatbot')
def chatbot():
    return render_template('chatbot.html')

@app.route('/askAns')
def askAns():
    return render_template('askAns.html')

@app.route('/startInterview')
def sI():
    return render_template('sI.html')

@app.route('/result/<session_id>')
def result(session_id):
    responses = interview_results.get(session_id, [])
    return render_template('Iresult.html', responses=responses)

if __name__ == '__main__':
    app.run(debug=True)
