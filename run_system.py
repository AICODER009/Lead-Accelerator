import os
import sys
import time
import socket
import subprocess
import signal
from dotenv import load_dotenv

# Force UTF-8 encoding for stdout/stderr to prevent UnicodeEncodeErrors on Windows
os.environ["PYTHONIOENCODING"] = "utf-8"

# Load environment variables from .env
load_dotenv()

# Configuration
QUIZ_PORT = 9001
BUDDY_PORT = 9002
STREAMLIT_PORT = 8501

def is_port_open(host: str, port: int) -> bool:
    """Check if a local port is open/active."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.settimeout(0.5)
            s.connect((host, port))
            return True
        except (socket.timeout, ConnectionRefusedError):
            return False

def format_msg(title: str, text: str, color_code: str = "32"):
    """Print formatted terminal message."""
    print(f"\033[1;{color_code}m[{title}]\033[0m {text}")

def main():
    print("=" * 65)
    print(" B2B Lead Accelerator Studio - Chapter 9 System Assembly".center(65))
    print("=" * 65)
    
    # 1. Active virtual environment detection & python executable selection
    python_exe = sys.executable
    format_msg("System", f"Using python executable: {python_exe}")
    
    processes = []
    
    try:
        # 2. Boot up Objection / Simulation Service (Port 9001)
        format_msg("Services", "Spawning B2B Sales Objection Simulator Service on port 9001...")
        proc_quiz = subprocess.Popen(
            [python_exe, "src/a2a_services/objection_service.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=os.environ.copy()
        )
        processes.append(proc_quiz)
        
        # 3. Boot up Sales Research Partner Service (Port 9002)
        format_msg("Services", "Spawning CrewAI Sales Research Partner Service on port 9002...")
        proc_buddy = subprocess.Popen(
            [python_exe, "src/a2a_services/sales_research_partner.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=os.environ.copy()
        )
        processes.append(proc_buddy)
        
        # 4. Wait for microservice ports to become active
        format_msg("System", "Polling ports 9001 and 9002 for readiness...")
        start_time = time.time()
        timeout = 15.0  # seconds
        
        while True:
            quiz_ok = is_port_open("127.0.0.1", QUIZ_PORT)
            buddy_ok = is_port_open("127.0.0.1", BUDDY_PORT)
            
            if quiz_ok and buddy_ok:
                format_msg("System", "Both A2A microservices are fully active and reachable!")
                break
                
            if time.time() - start_time > timeout:
                format_msg("Warning", "A2A services took longer than expected to boot. Starting UI anyway...", "33")
                break
                
            time.sleep(0.5)
            
        # 5. Boot up Streamlit Studio UI Dashboard
        format_msg("UI", "Starting Streamlit Studio Dashboard...")
        streamlit_cmd = [
            python_exe, "-m", "streamlit", "run", "app.py",
            "--server.port", str(STREAMLIT_PORT)
        ]
        
        # We allow streamlit to print to terminal stdout/stderr
        proc_streamlit = subprocess.Popen(
            streamlit_cmd,
            env=os.environ.copy()
        )
        processes.append(proc_streamlit)
        
        format_msg("Success", "Complete System assembled successfully!", "35")
        format_msg("System", "Press Ctrl+C to terminate all services and exit cleanly.\n")
        
        # Wait for Streamlit to exit
        proc_streamlit.wait()
        
    except KeyboardInterrupt:
        print("\n" + "=" * 65)
        format_msg("System", "Keyboard interrupt received. Shutting down all services...")
    finally:
        # Gracefully terminate all spawned processes
        for p in processes:
            if p.poll() is None:  # Process is still running
                try:
                    format_msg("System", f"Terminating process with PID {p.pid}...")
                    p.terminate()
                    p.wait(timeout=2)
                except Exception:
                    p.kill()
        print("=" * 65)
        format_msg("System", "All background microservices shut down successfully.")
        print("=" * 65)

if __name__ == "__main__":
    main()
