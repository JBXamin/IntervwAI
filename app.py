import json
import os
from uuid import uuid4
import google.generativeai as genai
from flask import Flask, render_template, request, jsonify, url_for, redirect
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Set the path to the credentials.json file
SERVICE_ACCOUNT_FILE = 'credentials.json'
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = SERVICE_ACCOUNT_FILE

# Set the API key from the environment variable
genai.api_key = "AIzaSyDcw5qJwF3KkDNZI2cG_9vVvCDjLLMXGik"

qsns = 0
conversation_history = []
responses = []

questions = [
    "What is your greatest strength?",
    "Why do you want to work here?",
    "Tell me about a challenge you faced and how you overcame it.",
    "How do you handle stress and pressure?",
    "Describe a time when you demonstrated leadership."
]

interview_results = {}


def generate_response(query):
    global conversation_history
    model = genai.GenerativeModel('gemini-1.5-flash-latest')

    current_conversation = "\n".join(conversation_history[-2:] + [f"user: {query}"])
    response = model.generate_content(current_conversation)

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
    global qsns, responses, conversation_history
    data = request.json
    user_message = data.get('message', '')

    if not user_message:
        return jsonify({'response': 'No message provided'}), 400

    try:
        current_question = questions[qsns]
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
        print(f"Response stored: {response_entry}")  # Debug statement

        qsns += 1
        if qsns >= 3:
            session_id = str(uuid4())
            interview_results[session_id] = responses.copy()
            qsns = 0
            conversation_history.clear()
            responses.clear()
            return jsonify({
                'response': ai_response,
                'redirect': url_for('iresult', session_id=session_id)
            })

        conversation_history = conversation_history[-1:]

        return jsonify({'response': ai_response})
    except Exception as e:
        return jsonify({'response': f'Error: {str(e)}'}), 500


@app.route('/')
def home():
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


@app.route('/iresult/<session_id>')
def iresult(session_id):
    responses = interview_results.get(session_id, [])
    return render_template('Iresult.html', responses=responses)


if __name__ == '__main__':
    app.run(debug=True)
