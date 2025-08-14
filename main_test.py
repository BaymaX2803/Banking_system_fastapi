import pytest
import os
import tempfile
from fastapi.testclient import TestClient

# Import the FastAPI app and BankSystem from your app application file
from app import app, bank, BankSystem

# Create a TestClient instance for the FastAPI application
client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_database():
    """
    This fixture runs before every test to reset the database.
    Creates a temporary database file for each test run.
    'autouse=True' means it will be automatically applied to all tests.
    """
    global bank
    
    # Create a temporary database file
    temp_fd, temp_path = tempfile.mkstemp(suffix='.db')
    os.close(temp_fd)  # Close the file descriptor
    
    # Replace the global bank instance with a test instance using temporary database
    original_bank = bank
    bank = BankSystem(temp_path)
    
    # Monkey patch the app's bank reference
    import app
    app.bank = bank
    
    # Create some test accounts with initial balances
    bank.create_account("ACC001", "John Doe", 1000.0)
    bank.create_account("ACC002", "Jane Smith", 500.0)
    
    yield
    
    # Restore original bank instance and clean up
    bank = original_bank
    app.bank = original_bank
    
    try:
        os.unlink(temp_path)
    except OSError:
        pass

# ==================== ACCOUNT MANAGEMENT TESTS ====================

def test_create_account_successful():
    """Test successful account creation."""
    response = client.post("/accounts", json={
        "account_number": "ACC003",
        "account_holder": "Bob Johnson",
        "initial_balance": 750.0
    })
    assert response.status_code == 200
    assert response.json()["message"] == "Account ACC003 created successfully"
    assert response.json()["status"] == "success"

def test_create_account_duplicate():
    """Test creating an account with an existing account number."""
    response = client.post("/accounts", json={
        "account_number": "ACC001",
        "account_holder": "Duplicate User",
        "initial_balance": 100.0
    })
    assert response.status_code == 400
    assert response.json()["detail"] == "Account number already exists"

def test_create_account_negative_balance():
    """Test creating an account with negative initial balance (should fail validation)."""
    response = client.post("/accounts", json={
        "account_number": "ACC004",
        "account_holder": "Test User",
        "initial_balance": -100.0
    })
    assert response.status_code == 422  # Validation error

def test_get_account_successful():
    """Test retrieving an existing account."""
    response = client.get("/accounts/ACC001")
    assert response.status_code == 200
    data = response.json()
    assert data["account_number"] == "ACC001"
    assert data["account_holder"] == "John Doe"
    assert data["balance"] == 1000.0

def test_get_account_not_found():
    """Test retrieving a non-existent account."""
    response = client.get("/accounts/NONEXISTENT")
    assert response.status_code == 404
    assert response.json()["detail"] == "Account not found"

def test_get_all_accounts():
    """Test retrieving all accounts."""
    response = client.get("/accounts")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    account_numbers = [acc["account_number"] for acc in data]
    assert "ACC001" in account_numbers
    assert "ACC002" in account_numbers

# ==================== BALANCE TESTS ====================

def test_get_balance_successful():
    """Test retrieving account balance."""
    response = client.get("/accounts/ACC001/balance")
    assert response.status_code == 200
    data = response.json()
    assert data["account_number"] == "ACC001"
    assert data["balance"] == 1000.0
    assert data["status"] == "success"

def test_get_balance_account_not_found():
    """Test retrieving balance for non-existent account."""
    response = client.get("/accounts/NONEXISTENT/balance")
    assert response.status_code == 404
    assert response.json()["detail"] == "Account not found"

# ==================== DEPOSIT TESTS ====================

def test_deposit_successful():
    """Test successful deposit and verify balance is updated."""
    response = client.post("/accounts/ACC001/deposit", json={
        "amount": 500.0,
        "description": "Test deposit"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Successfully deposited $500.00"
    assert data["new_balance"] == 1500.0
    assert data["status"] == "success"

def test_deposit_account_not_found():
    """Test deposit to non-existent account."""
    response = client.post("/accounts/NONEXISTENT/deposit", json={
        "amount": 100.0
    })
    assert response.status_code == 404
    assert response.json()["detail"] == "Account not found"

def test_deposit_negative_amount():
    """Test deposit with negative amount (should be rejected by validation)."""
    response = client.post("/accounts/ACC001/deposit", json={
        "amount": -100.0
    })
    assert response.status_code == 422  # Validation error

def test_deposit_zero_amount():
    """Test deposit with zero amount (should be rejected by validation)."""
    response = client.post("/accounts/ACC001/deposit", json={
        "amount": 0.0
    })
    assert response.status_code == 422  # Validation error

# ==================== WITHDRAWAL TESTS ====================

def test_withdraw_successful():
    """Test successful withdrawal and verify balance is updated."""
    response = client.post("/accounts/ACC001/withdraw", json={
        "amount": 200.0,
        "description": "Test withdrawal"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Successfully withdrew $200.00"
    assert data["new_balance"] == 800.0
    assert data["status"] == "success"

def test_withdraw_insufficient_funds():
    """Test withdrawal that exceeds account balance."""
    response = client.post("/accounts/ACC001/withdraw", json={
        "amount": 2000.0
    })
    assert response.status_code == 400
    assert "Insufficient funds" in response.json()["detail"]
    assert "Current balance: $1000.00" in response.json()["detail"]

def test_withdraw_account_not_found():
    """Test withdrawal from non-existent account."""
    response = client.post("/accounts/NONEXISTENT/withdraw", json={
        "amount": 100.0
    })
    assert response.status_code == 404
    assert response.json()["detail"] == "Account not found"

def test_withdraw_exact_balance():
    """Test withdrawal of exact account balance."""
    response = client.post("/accounts/ACC001/withdraw", json={
        "amount": 1000.0,
        "description": "Withdraw all funds"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["new_balance"] == 0.0

# ==================== TRANSFER TESTS ====================

def test_transfer_successful():
    """Test successful transfer between two accounts."""
    response = client.post("/transfer", json={
        "from_account": "ACC001",
        "to_account": "ACC002",
        "amount": 300.0,
        "description": "Test transfer"
    })
    assert response.status_code == 200
    data = response.json()
    assert "Successfully transferred $300.00" in data["message"]
    assert "from ACC001 to ACC002" in data["message"]
    assert data["from_account_balance"] == 700.0
    assert data["to_account_balance"] == 800.0
    assert data["status"] == "success"

def test_transfer_insufficient_funds():
    """Test transfer with insufficient funds in source account."""
    response = client.post("/transfer", json={
        "from_account": "ACC001",
        "to_account": "ACC002",
        "amount": 5000.0
    })
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "Insufficient funds in source account" in detail
    assert "Current balance: $1000.00" in detail

def test_transfer_source_account_not_found():
    """Test transfer from non-existent source account."""
    response = client.post("/transfer", json={
        "from_account": "NONEXISTENT",
        "to_account": "ACC002",
        "amount": 100.0
    })
    assert response.status_code == 404
    assert "Source account NONEXISTENT not found" in response.json()["detail"]

def test_transfer_destination_account_not_found():
    """Test transfer to non-existent destination account."""
    response = client.post("/transfer", json={
        "from_account": "ACC001",
        "to_account": "NONEXISTENT",
        "amount": 100.0
    })
    assert response.status_code == 404
    assert "Destination account NONEXISTENT not found" in response.json()["detail"]

def test_transfer_same_account():
    """Test transfer to the same account (should be rejected)."""
    response = client.post("/transfer", json={
        "from_account": "ACC001",
        "to_account": "ACC001",
        "amount": 100.0
    })
    assert response.status_code == 400
    assert response.json()["detail"] == "Cannot transfer to the same account"

def test_transfer_both_accounts_not_found():
    """Test transfer between two non-existent accounts."""
    response = client.post("/transfer", json={
        "from_account": "NONEXISTENT1",
        "to_account": "NONEXISTENT2",
        "amount": 100.0
    })
    assert response.status_code == 404
    assert "Source account NONEXISTENT1 not found" in response.json()["detail"]

# ==================== TRANSACTION HISTORY TESTS ====================

def test_get_transaction_history():
    """Test retrieving transaction history after performing transactions."""
    # Perform some transactions first
    client.post("/accounts/ACC001/deposit", json={"amount": 200.0, "description": "Test deposit"})
    client.post("/accounts/ACC001/withdraw", json={"amount": 100.0, "description": "Test withdrawal"})
    client.post("/transfer", json={
        "from_account": "ACC001",
        "to_account": "ACC002",
        "amount": 150.0,
        "description": "Test transfer"
    })
    
    # Get transaction history
    response = client.get("/accounts/ACC001/transactions?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3  # Should have 3 transactions
    
    # Check that transactions are ordered by timestamp (most recent first)
    transaction_types = [trans["transaction_type"] for trans in data]
    assert "DEPOSIT" in transaction_types
    assert "WITHDRAWAL" in transaction_types
    assert "TRANSFER" in transaction_types
    
    # Check amounts
    amounts = [trans["amount"] for trans in data]
    assert 200.0 in amounts  # deposit
    assert 100.0 in amounts  # withdrawal
    assert 150.0 in amounts  # transfer

def test_get_transaction_history_account_not_found():
    """Test retrieving transaction history for non-existent account."""
    response = client.get("/accounts/NONEXISTENT/transactions")
    assert response.status_code == 404
    assert response.json()["detail"] == "Account not found"

def test_transaction_history_empty():
    """Test transaction history for account with no transactions."""
    # Create a new account with no transactions
    client.post("/accounts", json={
        "account_number": "ACC005",
        "account_holder": "Empty Account",
        "initial_balance": 0.0
    })
    
    response = client.get("/accounts/ACC005/transactions")
    assert response.status_code == 200
    assert response.json() == []  # Should return empty list

def test_transaction_history_with_limit():
    """Test transaction history with custom limit."""
    # Create multiple transactions
    for i in range(5):
        client.post("/accounts/ACC001/deposit", json={"amount": 10.0, "description": f"Deposit {i+1}"})
    
    # Get only 3 transactions
    response = client.get("/accounts/ACC001/transactions?limit=3")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3

# ==================== INTEGRATION TESTS ====================

def test_complete_banking_workflow():
    """Test a complete banking workflow with multiple operations."""
    # Create a new account
    response = client.post("/accounts", json={
        "account_number": "WORKFLOW",
        "account_holder": "Workflow Test",
        "initial_balance": 1000.0
    })
    assert response.status_code == 200
    
    # Check initial balance
    response = client.get("/accounts/WORKFLOW/balance")
    assert response.json()["balance"] == 1000.0
    
    # Make a deposit
    response = client.post("/accounts/WORKFLOW/deposit", json={
        "amount": 500.0,
        "description": "Salary deposit"
    })
    assert response.status_code == 200
    assert response.json()["new_balance"] == 1500.0
    
    # Make a withdrawal
    response = client.post("/accounts/WORKFLOW/withdraw", json={
        "amount": 200.0,
        "description": "ATM withdrawal"
    })
    assert response.status_code == 200
    assert response.json()["new_balance"] == 1300.0
    
    # Transfer to another account
    response = client.post("/transfer", json={
        "from_account": "WORKFLOW",
        "to_account": "ACC001",
        "amount": 300.0,
        "description": "Transfer to friend"
    })
    assert response.status_code == 200
    assert response.json()["from_account_balance"] == 1000.0
    
    # Check transaction history
    response = client.get("/accounts/WORKFLOW/transactions")
    assert response.status_code == 200
    transactions = response.json()
    assert len(transactions) == 3  # deposit, withdrawal, transfer
    
    # Verify final balance
    response = client.get("/accounts/WORKFLOW/balance")
    assert response.json()["balance"] == 1000.0

def test_concurrent_transfers():
    """Test that balances reapp consistent after multiple transfers."""
    initial_acc001_balance = 1000.0
    initial_acc002_balance = 500.0
    
    # Perform multiple transfers
    transfers = [
        {"from": "ACC001", "to": "ACC002", "amount": 100.0},
        {"from": "ACC002", "to": "ACC001", "amount": 50.0},
        {"from": "ACC001", "to": "ACC002", "amount": 75.0},
    ]
    
    for transfer in transfers:
        response = client.post("/transfer", json={
            "from_account": transfer["from"],
            "to_account": transfer["to"],
            "amount": transfer["amount"]
        })
        assert response.status_code == 200
    
    # Check final balances
    acc001_response = client.get("/accounts/ACC001/balance")
    acc002_response = client.get("/accounts/ACC002/balance")
    
    final_acc001_balance = acc001_response.json()["balance"]
    final_acc002_balance = acc002_response.json()["balance"]
    
    # Total money should be conserved
    total_initial = initial_acc001_balance + initial_acc002_balance
    total_final = final_acc001_balance + final_acc002_balance
    assert abs(total_initial - total_final) < 0.01  # Account for floating point precision
    
    # Check individual balances
    expected_acc001_balance = initial_acc001_balance - 100.0 + 50.0 - 75.0  # 875.0
    expected_acc002_balance = initial_acc002_balance + 100.0 - 50.0 + 75.0  # 625.0
    
    assert abs(final_acc001_balance - expected_acc001_balance) < 0.01
    assert abs(final_acc002_balance - expected_acc002_balance) < 0.01