import json
import os
import google.generativeai as genai
from flask import Flask, render_template, request, jsonify, url_for, redirect
from flask_cors import CORS
from google.auth.exceptions import DefaultCredentialsError
from uuid import uuid4

app = Flask(__name__)
CORS(app)
SERVICE_ACCOUNT_FILE = 'credentials.json'
if not os.path.isfile(SERVICE_ACCOUNT_FILE):
    print(f"Error: The file {SERVICE_ACCOUNT_FILE} does not exist.")
else:
    try:
        with open(SERVICE_ACCOUNT_FILE) as f:
            credentials = json.load(f)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = SERVICE_ACCOUNT_FILE
    except json.JSONDecodeError as e:
        print(f"Error: File {SERVICE_ACCOUNT_FILE} is not a valid JSON file. Details: {e}")
        credentials = None

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



def init_db():
    conn = sqlite3.connect('interview_db.sqlite')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS tasks (
                        task_id TEXT PRIMARY KEY,
                        status TEXT,
                        start_time TEXT,
                        user_id TEXT,
                        user_message TEXT,
                        initial_prompt TEXT,
                        result TEXT,
                        processing_duration REAL
                    )''')
    conn.commit()
    conn.close()



task_queue = Queue()


def task_worker():
    while True:
        task = task_queue.get()
        if task is None:
            break
        process_task(task)



def process_task(task):
    task_id = task['task_id']
    task['status'] = 'in progress'
    update_task_in_db(task)
    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        prompt = f"{task['initial_prompt']}\nuser: {task['user_message']}"
        response = model.generate_content(prompt)
        text_content = response.candidates[0].content.parts[0].text
        task['status'] = 'success'
        task['result'] = text_content
    except Exception as e:
        task['status'] = 'error'
        task['error'] = str(e)
    finally:
        task['processing_duration'] = (datetime.now() - datetime.fromisoformat(task['start_time'])).total_seconds()
        update_task_in_db(task)


def update_task_in_db(task):
    conn = sqlite3.connect('interview_db.sqlite')
    cursor = conn.cursor()
    cursor.execute('''REPLACE INTO tasks (task_id, status, start_time, user_id, user_message, initial_prompt, result, processing_duration)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                   (task['task_id'], task['status'], task['start_time'], task['user_id'], task['user_message'],
                    task['initial_prompt'], task.get('result', ''), task.get('processing_duration', 0)))
    conn.commit()
    conn.close()



worker_thread = Thread(target=task_worker)
worker_thread.start()


@app.route('/call', methods=['POST'])
def call_api():
    global qsns, responses, conversation_history, generated_questions
    try:
        data = request.json
        task_id = str(uuid.uuid4())
        user_message = data.get('message', '')

        if not user_message:
            return jsonify({'response': 'No message provided'}), 400

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
        if qsns >= 5:
            session_id = str(uuid.uuid4())
            interview_results[session_id] = responses.copy()
            qsns = 0
            conversation_history.clear()
            responses.clear()
            generated_questions.clear()

            
            task = {
                'task_id': task_id,
                'status': 'success',
                'start_time': datetime.now().isoformat(),
                'user_id': request.headers.get('x-user-id', 'unknown'),
                'user_message': user_message,
                'initial_prompt': INITIAL_PROMPT,
                'result': ai_response,
                'processing_duration': 0,
            }
            update_task_in_db(task)
            task_queue.put(task)

            redirect_url = url_for('result_page', session_id=session_id)

            response = {
                "requestId": request.headers.get('x-request-id', ''),
                "traceId": str(uuid.uuid4()),
                "apiVersion": "1.0.1",
                "service": "InterviewService",
                "datetime": datetime.now().isoformat(),
                "isResponseImmediate": True,
                "extraType": "others",
                "response": {
                    "taskId": task_id,
                    "redirect": redirect_url,
                    "question": ai_response
                },
                "errorCode": {
                    "status": "AC_000",
                    "reason": "success"
                }
            }
            app.logger.info(f"Redirecting to result page: {redirect_url}")
            return jsonify(response), 200

        conversation_history = conversation_history[-1:]

        response = {
            "requestId": request.headers.get('x-request-id', ''),
            "traceId": str(uuid.uuid4()),
            "apiVersion": "1.0.1",
            "service": "InterviewService",
            "datetime": datetime.now().isoformat(),
            "isResponseImmediate": True,
            "extraType": "others",
            "response": {
                "taskId": task_id,
                "question": current_question,
            },
            "errorCode": {
                "status": "AC_001",
                "reason": "pending"
            }
        }
        return jsonify(response), 200

    except BadRequest:
        app.logger.error('Bad request format encountered.', exc_info=True)
        return jsonify({'error': 'Invalid request format.'}), 400
    except Exception as e:
        app.logger.error(f"Error in /call API: {str(e)}", exc_info=True)
        return jsonify({'error': f'Internal Server Error: {str(e)}'}), 500


@app.route('/result', methods=['POST'])
def result_api():
    try:
        task_id = request.json.get('taskId')
        conn = sqlite3.connect('interview_db.sqlite')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM tasks WHERE task_id = ?', (task_id,))
        task = cursor.fetchone()
        conn.close()

        if not task:
            app.logger.error(f"Task with taskId {task_id} not found.")
            return jsonify({
                "errorCode": {"status": "AC_404", "reason": "taskId not found"}
            }), 404

        response = {
            "apiVersion": "1.0.1",
            "service": "InterviewService",
            "datetime": datetime.now().isoformat(),
            "processDuration": task[7],  # Adjust index based on your schema
            "isResponseImmediate": False,
            "extraType": "others",
            "response": {
                "dataType": "META_DATA",
                "data": task[6]  # Adjust index based on your schema
            },
            "errorCode": {
                "status": "AC_000" if task[1] == 'success' else "AC_002",
                "reason": task[1]
            }
        }
        app.logger.info(f"Successfully fetched result for taskId: {task_id}")
        return jsonify(response), 200

    except BadRequest:
        app.logger.error('Bad request format encountered in /result.', exc_info=True)
        return jsonify({'error': 'Invalid request format.'}), 400
    except Exception as e:
        app.logger.error(f"Error in /result API: {str(e)}", exc_info=True)
        return jsonify({'error': f'Internal Server Error: {str(e)}'}), 500


def generate_response(query, initial_prompt=INITIAL_PROMPT):
    global conversation_history
    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        current_conversation = "\n".join(conversation_history[-2:] + [f"user: {query}"])
        full_prompt = f"{initial_prompt}\n{current_conversation}"
        response = model.generate_content(full_prompt)
        text_content = response.candidates[0].content.parts[0].text
        conversation_history.append(f"ai: {text_content}")

        return text_content
    except Exception as e:
        app.logger.error(f"Error generating AI response: {str(e)}", exc_info=True)
        raise e


def evaluate_answer(question, answer):
    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        prompt = (
            f"Question: {question}\nAnswer: {answer}\nEvaluate the above answer as an interview response. Provide a "
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
    except Exception as e:
        app.logger.error(f"Error in evaluate_answer: {str(e)}", exc_info=True)
        raise e


@app.route('/')
def home():
    global qsns
    qsns = 0
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
def result_page(session_id):
    responses = interview_results.get(session_id, [])
    return render_template('Iresult.html', responses=responses)


if __name__ == '__main__':
    init_db()
    app.run(debug=True)

