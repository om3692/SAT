# SATInsight: Digital SAT Diagnostic Test Platform

## Project Overview

SATInsight is a web-based application designed to help students prepare for the Digital SAT. It provides a simulated test environment where users can take a diagnostic test, receive a predicted score, identify areas for improvement, and track their progress. The platform aims to offer a user-friendly experience with features that mirror aspects of the actual Digital SAT.

## Features

* **User Authentication**: Secure registration and login functionality for users to track their progress and scores.
* **Timed Diagnostic Tests**: Simulates the timed nature of the SAT, with a predefined set of questions for Math and Reading & Writing sections.
* **Question Presentation**: Questions are presented one at a time for focused attention.
* **Navigation & Review**: Users can navigate between questions ("Next", "Back") and mark questions for review.
* **Passage Handling**: For Reading & Writing questions, passages are displayed alongside the questions, with an option to hide/show the passage.
* **In-Test Tools**:
    * On-screen calculator available for Math questions.
    * Test directions accessible during the test.
* **Automated Scoring**: Calculates a mock total score, as well as scores for Math and Reading & Writing sections based on user answers.
* **Results Dashboard**: Displays past test scores, including overall score, section scores, and number of correct answers.
* **Performance Analysis**: Provides a summary of performance, identifies potential areas for improvement (weaknesses), and offers general study recommendations.
* **CSV Report Download**: Users can download a detailed CSV report of their test attempt, including each question, their answer, the correct answer, and question metadata.
* **Session Management**: Tracks test progress within a session and clears the session upon test completion or reset.
* **Custom Error Pages**: User-friendly pages for 404 (Not Found) and 500 (Internal Server Error) errors.

## Technology Stack

* **Backend**: Python, Flask
* **Database**: SQLite (via Flask-SQLAlchemy)
* **Frontend**: HTML, Tailwind CSS, JavaScript
* **Password Hashing**: Werkzeug security helpers
* **Authentication**: Flask-Login

## File Structure
