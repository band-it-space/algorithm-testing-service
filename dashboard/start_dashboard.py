#!/usr/bin/env python3
"""
Script for RQ Dashboard
"""
import os
import subprocess
import sys

def main():
    """
    RQ Dashboard
    """
    redis_host = os.getenv('REDIS_HOST', 'localhost')
    redis_port = os.getenv('REDIS_PORT', '6379')
    redis_db = os.getenv('REDIS_DB', '0')
    dashboard_port = os.getenv('DASHBOARD_PORT', '9181')
    
    print("Starting RQ Dashboard...")
    print(f"Redis: {redis_host}:{redis_port}/{redis_db}")
    print(f"Dashboard: http://localhost:{dashboard_port}")
    
    cmd = [
        'rq-dashboard',
        '--port', dashboard_port,
        '--redis-host', redis_host,
        '--redis-port', redis_port,
        '--redis-database', redis_db
    ]
    
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    except Exception as e:
        print(f"Error starting dashboard: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
