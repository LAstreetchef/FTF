from app import app
import os

if __name__ == '__main__':
    # Use production settings when deployed
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)
