import os
import json
from flask import Flask, request, Response, send_from_directory
from agent import run_agent_streaming
from outreach_agent import send_outreach_from_discovery

app = Flask(__name__)

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/run', methods=['POST'])
def run():
    data = request.get_json()
    venture = data.get('venture', '').strip()
    if not venture:
        return Response('No venture description provided', status=400)

    def generate():
        try:
            for event in run_agent_streaming(venture):
                yield event + '\n'
        except Exception as e:
            yield f'ERROR:{str(e)}\n'

    return Response(generate(), mimetype='text/plain', headers={
        'X-Accel-Buffering': 'no',
        'Cache-Control': 'no-cache'
    })


@app.route('/send_outreach', methods=['POST'])
def send_outreach():
    """Send outreach email to first call target and log to CSV."""
    try:
        data = request.get_json()
        discovery_result = data.get('discovery_result', {})

        if not discovery_result:
            return {'success': False, 'message': 'No discovery result provided'}, 400

        result = send_outreach_from_discovery(discovery_result)

        if result['success']:
            return {
                'success':           True,
                'message':           result['message'],
                # contact card fields
                'linkedin':          result.get('linkedin', ''),
                'email':             result.get('email', ''),
                'email_source':      result.get('email_source', ''),
                'email_note':        result.get('email_note', ''),
                'phone':             result.get('phone', ''),
                'phone_source':      result.get('phone_source', 'not_found'),
                'website':           result.get('website', ''),
                'twitter':           result.get('twitter', ''),
                # follow-up
                'follow_up_date':    result.get('follow_up_date', ''),
                'followup_template': result.get('followup_template', ''),
                'all_targets':       result.get('all_targets', []),
            }, 200
        else:
            return {
                'success': False,
                'message': result['message']
            }, 400

    except Exception as e:
        return {
            'success': False,
            'message': f'Server error: {str(e)}'
        }, 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f'\n→ Discovery Agent running at http://localhost:{port}\n')
    app.run(host='0.0.0.0', port=port, debug=False)
