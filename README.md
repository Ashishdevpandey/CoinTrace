# CoinTrace 🪙

CoinTrace is a modern, full-stack personal finance dashboard designed to help you track your income, expenses, and account balances with ease. It features a sleek, dark-themed UI and interactive charts for data visualization.

## Features

-   **Dashboard Overview**: View total balance, monthly spending, and savings goals at a glance.
-   **Interactive Charts**:
    -   **Income vs Expense**: A smooth line graph visualizing your financial trends over the last 6 months.
    -   **Spending by Category**: A doughnut chart breaking down your expenses (Food, Transport, Shopping, etc.).
-   **Transaction Management**: Add new income or expense transactions via a modal interface.
-   **Analytics View**: Detailed list of all transactions and spending trends.
-   **Accounts View**: Monitor balances for different accounts (Checking, Savings).
-   **Settings**: Customizable user profile and currency settings (Default: INR ₹).
-   **Responsive Design**: Works seamlessly on different screen sizes.

## Tech Stack

-   **Backend**: Python (Flask), SQLite
-   **Frontend**: HTML5, CSS3, JavaScript (Vanilla)
-   **Libraries**: Chart.js (for graphs), FontAwesome (for icons)

## Installation & Setup

1.  **Clone the repository** (or download the source code):
    ```bash
    git clone https://github.com/Ashishdevpandey/CoinTrace.git
    cd CoinTrace
    ```

2.  **Install Dependencies**:
    Make sure you have Python installed. Then install the required Flask packages:
    ```bash
    pip install flask flask-cors
    ```

3.  **Run the Application**:
    Start the Flask backend server:
    ```bash
    python3 app.py
    ```
    *The application will automatically initialize the `banking.db` SQLite database and seed it with sample data on the first run.*

4.  **Access the Dashboard**:
    Open your web browser and navigate to:
    [http://localhost:5000](http://localhost:5000)

    *Alternatively, you can open the `templates/index.html` file directly in your browser, as the app supports `file://` protocol access via CORS.*

## Project Structure

-   `app.py`: The Flask backend handling API endpoints and database operations.
-   `templates/index.html`: The single-page frontend containing HTML, CSS, and JavaScript.
-   `banking.db`: SQLite database file (generated automatically).

## Usage

-   **Add Transaction**: Click the floating "+" button in the bottom right corner.
-   **Navigation**: Use the sidebar to switch between Dashboard, Analytics, Accounts, and Settings.
-   **Reset Data**: To reset the application data, simply delete the `banking.db` file and restart `app.py`.

## License

This project is open-source and available for personal use and modification.
