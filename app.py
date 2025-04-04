# app.py
import streamlit as st
import os
from datetime import datetime
from dotenv import load_dotenv
import json
import logging
from logging.handlers import RotatingFileHandler


PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(PROJECT_DIR,'logs')

log_file_path = os.path.join(LOG_DIR,'log_advisor_log')

# Set up logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s -%(message)s',
                    handlers=[logging.StreamHandler(),RotatingFileHandler(log_file_path,maxBytes=5242880,backupCount=3)])
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Import service modules (create these files next)
from services.elk_service import ELKService
from services.vegasgpt_service import VegasGPTService
from services.synapt_service import SynaptService

# Page configuration
st.set_page_config(
    page_title="Log Advisor",
    page_icon="🔍",
    layout="wide"
)

# Application title and description
st.title("Log Advisor")
st.markdown("**Diagnose and resolve errors from system logs**")
st.markdown("---")

# Initialize services
elk_service = ELKService()
vegasgpt_service = VegasGPTService()
synapt_service = SynaptService()

# Input form
st.header("Search Parameters")

with st.form("log_search_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        work_order = st.text_input("Work Order Number")
        start_date = st.date_input("Last Transaction Start Date")
        start_time = st.time_input("Last Transaction Start Time")

    with col2:
        task_name = st.text_input("Task Name")
        end_date = st.date_input("Last Transaction End Date")
        end_time = st.time_input("Last Transaction End Time")

    submit_button = st.form_submit_button("Analyze Logs")

# Process the form submission
if submit_button:
    # Input validation
    if not work_order or not task_name:
        st.error("Work Order and Task Name are required fields")
    elif end_time <= start_time:
        st.error("End time must be after start time")
    else:
        # Show a progress bar for the analysis steps
        progress_bar = st.progress(0)
        st.markdown("### Analysis Progress")
        status_text = st.empty()
        
        # Step 1: Retrieve logs from ELK
        status_text.text("Retrieving logs from ELK...")
        
        # Format dates for ELK query
        start_datetime = datetime.combine(start_date,start_time)
        end_datetime = datetime.combine(end_date,end_time)

        start_time_str = start_datetime.strftime('%Y-%m-%dT%H:%M:%S.%f')
        end_time_str = end_datetime.strftime('%Y-%m-%dT%H:%M:%S.%f')
        
        logs = elk_service.retrieve_logs(work_order, task_name, start_time_str, end_time_str)
        progress_bar.progress(33)
        
        if logs is None:
            st.error("Error connecting to the log service. Please check your connection and try again.")
        elif not logs:
            st.warning("No logs found for the specified criteria.")
        else:
            # Step 2: Analyze logs with Google Gemini
            status_text.text("Analyzing logs with AI Service...")
            error_analysis = vegasgpt_service.analyze_logs(logs)
            progress_bar.progress(66)
            
            # Step 3: Find solutions from Synapt
            status_text.text("Finding solutions from Synapt...")
            if error_analysis and error_analysis.get('errors'):
                solution = synapt_service.find_solutions(error_analysis.get('errors'))
            else:
                solution = {"recommendations": [], "summary": "No errors to find solutions for."}
            
            progress_bar.progress(100)
            status_text.text("Analysis complete!")
            
            # Display results in tabs
            st.markdown("## Analysis Results")
            
            tab1, tab2, tab3 = st.tabs(["Retrieved Logs", "Error Analysis", "Recommended Solutions"])
            
            # Tab 1: Retrieved Logs
            with tab1:
                st.subheader(f"Logs ({len(logs)})")
                
                # Filter options
                log_level_filter = st.multiselect(
                    "Filter by Log Level",
                    options=["INFO", "WARNING", "ERROR", "DEBUG", "TRACE"],
                    default=["INFO", "WARNING", "ERROR"]
                )
                
                # Show logs with filtering
                filtered_logs = [log for log in logs if log.get('level', '').upper() in log_level_filter]
                
                st.text(f"Showing {len(filtered_logs)} of {len(logs)} logs")
                
                for log in filtered_logs:
                    level = log.get('level', '').upper()
                    timestamp = log.get('timestamp', '')
                    message = log.get('message', '')
                    service = log.get('service', 'unknown')
                    
                    # Style based on log level
                    if level in ['ERROR', 'SEVERE']:
                        st.error(f"[{timestamp}] [{service}] {message}")
                    elif level in ['WARNING', 'WARN']:
                        st.warning(f"[{timestamp}] [{service}] {message}")
                    else:
                        st.info(f"[{timestamp}] [{service}] {message}")
            
            # Tab 2: Error Analysis
            with tab2:
                if error_analysis and error_analysis.get('errors'):
                    st.subheader("Detected Errors")
                    st.markdown(f"**Summary**: {error_analysis.get('summary', 'No summary available')}")
                    
                    for i, error in enumerate(error_analysis.get('errors', [])):
                        with st.expander(f"Error #{i+1}: {error.get('message', '')[:50]}...", expanded=i == 0):
                            st.markdown(f"**Severity**: {error.get('severity', 'Unknown')}")
                            st.markdown("**Error Message**:")
                            st.code(error.get('message', 'No message available'))
                            
                            st.markdown("**Root Cause**:")
                            st.write(error.get('root_cause', 'Unknown'))
                            
                            if error.get('timestamp'):
                                st.caption(f"Occurred at: {error.get('timestamp')}")
                else:
                    st.success("No errors detected in the logs.")
            
            # Tab 3: Solutions
            with tab3:
                if solution and solution.get('recommendations'):
                    st.subheader("Solution Recommendations")
                    st.markdown(f"**Summary**: {solution.get('summary', 'No summary available')}")
                    
                    for i, rec in enumerate(solution.get('recommendations', [])):
                        with st.expander(f"Solution #{i+1}", expanded=i == 0):
                            confidence = rec.get('confidence', 0)
                            confidence_percentage = int(confidence * 100)
                            
                            # Display confidence with color coding
                            if confidence_percentage >= 70:
                                st.markdown(f"**Confidence**: :green[{confidence_percentage}%]")
                            elif confidence_percentage >= 40:
                                st.markdown(f"**Confidence**: :orange[{confidence_percentage}%]")
                            else:
                                st.markdown(f"**Confidence**: :red[{confidence_percentage}%]")
                            
                            st.markdown("**For Error**:")
                            st.code(rec.get('error', 'Unknown error'))
                            
                            st.markdown("**Recommended Fix**:")
                            st.write(rec.get('solution', 'No solution available'))
                            
                            if rec.get('steps'):
                                st.markdown("**Steps to Resolve**:")
                                for j, step in enumerate(rec.get('steps')):
                                    st.markdown(f"{j+1}. {step}")
                else:
                    if error_analysis and error_analysis.get('errors'):
                        st.info("No solutions found for the detected errors.")
                    else:
                        st.success("No errors detected, no solutions needed.")

# Add helpful information in the sidebar
with st.sidebar:
    st.header("About Log Advisor")
    st.markdown("""
    **Log Advisor** helps you:
    
    - Retrieve system logs from ELK
    - Analyze logs for errors using Vegas GPT
    - Find solutions from the Synapt knowledge base
    
    Enter your search parameters and click "Analyze Logs" to get started.
    """)
    
    st.markdown("---")
    
    # Show connection status for services
    st.subheader("Service Status")
    elk_status = ":green[Connected]" if elk_service.is_configured() else ":red[Not Configured]"
    vegas_status = ":green[Connected]" if vegasgpt_service.is_configured() else ":red[Not Configured]"
    synapt_status = ":green[Connected]" if synapt_service.is_configured() else ":red[Not Configured]"
    
    st.markdown(f"ELK Service: {elk_status}")
    st.markdown(f"Vegas GPT Service: {vegas_status}")
    st.markdown(f"Synapt: {synapt_status}")

    with st.expander("Synapt Database Details"):
        if synapt_service.is_configured():
            st.text(f"Host: {synapt_service.db_host}")
            st.text(f"Database: {synapt_service.db_name}")
            st.text(f"User: {synapt_service.db_user}")

            if st.button("Test Synapt DB Connection"):
                success, message = synapt_service.test_connection()
                if success:
                    st.success(message)
                else:
                    st.error(message)
        else:
            st.error("Synapt database not configured")


       
