import os

from flask import (Flask, redirect, render_template, request,
                   send_from_directory, url_for)
import openai

from logging import INFO, getLogger
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry import trace
from opentelemetry.metrics import get_meter_provider
import json
from azure.identity import ManagedIdentityCredential

openai.api_type = "azure"
openai.api_key = os.environ.get("OPENAI_API_KEY")
openai.api_base = os.environ.get("OPENAI_API_BASE")
openai.api_version = "2023-05-15"

configure_azure_monitor(
    # Microsoft Entra ID 認証
    credential=ManagedIdentityCredential(),
)

app = Flask(__name__)
app.logger.setLevel(INFO)
FlaskInstrumentor().instrument_app(app)

tracer = trace.get_tracer(__name__)

@app.route('/')
def index():
   app.logger.info('Request for index page received')
   return render_template('index.html')

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/hello', methods=['POST'])
async def hello():
   name = request.form.get('name')
   trace.get_current_span().add_event("Hello request received", {"name": name})

   if name:
       app.logger.info('Request for hello page received with name=%s' % name)
       return render_template('hello.html', name = name, message = await generateMessage(name))
   else:
       app.logger.info('Request for hello page received with no name or blank name -- redirecting')
       return redirect(url_for('index'))

async def generateMessage(name):
    # Dependencies にログを出力
    with tracer.start_as_current_span("generateMessage") as span:
        try:
            messages = [
                {"role": "system", "content": "You are a system assistant. Please write a greeting for %s. Include some friendly banter in your greeting to make the reader feel happy. Think about the country of origin from the user's name and generate the message in that country's native language. " % name },
                {"role": "user", "content": "Hi, my name is %s." % name },
            ]
            # Traces にログを出力
            app.logger.info("Generating message for %s. Messages is %s" % (name, json.dumps(messages)))
            return await call_openai_chat_completion(messages)
        except Exception as e:
            # Exceptions にログを出力
            span.record_exception(e)
            # Traces にログを出力
            app.logger.error('Error generating message: %s' % e)
            return 'Error generating message: %s' % e

async def call_openai_chat_completion(messages):
    with tracer.start_as_current_span("call_openai_chat_completion", kind=trace.SpanKind.CLIENT):
        response = await openai.ChatCompletion.acreate(
            deployment_id="gpt-35-turbo",
            messages=messages,
            max_tokens=500,
            n=1,
            temperature=0.0,
        )
        return response.choices[0].message.content.strip()


if __name__ == '__main__':
   app.run()
