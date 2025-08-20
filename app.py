from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
import sqlite3
from datetime import datetime
import uvicorn


app = FastAPI(
    title="Bank Transaction System API",
    description="A simple banking system with account management and transactions",
    version="1.0.0"
)

# Pydantic models for request/response
class CreateAccountRequest(BaseModel):
    account_number: str = Field(..., description="Unique account number")
    account_holder: str = Field(..., description="Name of the account holder")
    initial_balance: float = Field(0.0, ge=0, description="Initial balance (must be non-negative)")

# FIXED: Separate models for deposit/withdraw (no account_number field)
class DepositWithdrawRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Transaction amount (must be positive)")
    description: Optional[str] = Field(None, description="Optional transaction description")

class TransferRequest(BaseModel):
    from_account: str = Field(..., description="Source account number")
    to_account: str = Field(..., description="Destination account number")
    amount: float = Field(..., gt=0, description="Transfer amount (must be positive)")
    description: Optional[str] = Field("Transfer", description="Optional transaction description")

class AccountResponse(BaseModel):
    account_number: str
    account_holder: str
    balance: float
    created_at: str

class TransactionResponse(BaseModel):
    transaction_type: str
    amount: float
    from_account: Optional[str]
    to_account: Optional[str]
    description: str
    timestamp: str

class BankSystem:
    def __init__(self, db_name: str = "bank_system.db"):
        self.db_name = db_name
        self.create_tables()

    def create_tables(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                account_id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_number TEXT UNIQUE NOT NULL,
                account_holder TEXT NOT NULL,
                balance DECIMAL(15,2) NOT NULL DEFAULT 0.00,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_account TEXT,
                to_account TEXT,
                transaction_type TEXT NOT NULL,
                amount DECIMAL(15,2) NOT NULL,
                description TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (from_account) REFERENCES accounts(account_number),
                FOREIGN KEY (to_account) REFERENCES accounts(account_number)
            )
        """)

        conn.commit()
        conn.close()

    def create_account(self, account_number: str, account_holder: str, initial_balance: float = 0.0) -> bool:
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO accounts (account_number, account_holder, balance)
                VALUES (?, ?, ?)
            """, (account_number, account_holder, initial_balance))
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_account(self, account_number: str):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("SELECT account_number, account_holder, balance, created_at FROM accounts WHERE account_number = ?", (account_number,))
        result = cursor.fetchone()
        conn.close()
        return result

    def get_all_accounts(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("SELECT account_number, account_holder, balance, created_at FROM accounts")
        results = cursor.fetchall()
        conn.close()
        return results

    def deposit(self, account_number: str, amount: float, description: str = "Deposit") -> bool:
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            
            cursor.execute("SELECT balance FROM accounts WHERE account_number = ?", (account_number,))
            result = cursor.fetchone()
            if not result:
                conn.close()
                return False

            current_balance = float(result[0])
            new_balance = current_balance + amount

            cursor.execute("UPDATE accounts SET balance = ? WHERE account_number = ?", (new_balance, account_number))
            cursor.execute("""
                INSERT INTO transactions (to_account, transaction_type, amount, description)
                VALUES (?, ?, ?, ?)
            """, (account_number, "DEPOSIT", amount, description))

            conn.commit()
            conn.close()
            return True
        except Exception:
            return False

    def withdraw(self, account_number: str, amount: float, description: str = "Withdrawal") -> bool:
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            
            cursor.execute("SELECT balance FROM accounts WHERE account_number = ?", (account_number,))
            result = cursor.fetchone()
            if not result:
                conn.close()
                return False

            current_balance = float(result[0])
            if current_balance < amount:
                conn.close()
                return False

            new_balance = current_balance - amount
            cursor.execute("UPDATE accounts SET balance = ? WHERE account_number = ?", (new_balance, account_number))
            cursor.execute("""
                INSERT INTO transactions (from_account, transaction_type, amount, description)
                VALUES (?, ?, ?, ?)
            """, (account_number, "WITHDRAWAL", amount, description))

            conn.commit()
            conn.close()
            return True
        except Exception:
            return False

    def transfer(self, from_account: str, to_account: str, amount: float, description: str = "Transfer") -> bool:
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute("BEGIN TRANSACTION")

            # Check both accounts exist and get balances
            cursor.execute("SELECT account_number, balance FROM accounts WHERE account_number IN (?, ?)", (from_account, to_account))
            accounts = cursor.fetchall()

            if len(accounts) != 2:
                cursor.execute("ROLLBACK")
                conn.close()
                return False

            account_balances = {acc[0]: float(acc[1]) for acc in accounts}
            from_balance = account_balances[from_account]

            if from_balance < amount:
                cursor.execute("ROLLBACK")
                conn.close()
                return False

            # Update balances
            cursor.execute("UPDATE accounts SET balance = balance - ? WHERE account_number = ?", (amount, from_account))
            cursor.execute("UPDATE accounts SET balance = balance + ? WHERE account_number = ?", (amount, to_account))

            # Record transaction
            cursor.execute("""
                INSERT INTO transactions (from_account, to_account, transaction_type, amount, description)
                VALUES (?, ?, ?, ?, ?)
            """, (from_account, to_account, "TRANSFER", amount, description))

            cursor.execute("COMMIT")
            conn.close()
            return True
        except Exception:
            return False

    def get_transaction_history(self, account_number: str, limit: int = 10):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT transaction_type, amount, from_account, to_account, description, timestamp
            FROM transactions
            WHERE from_account = ? OR to_account = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (account_number, account_number, limit))
        results = cursor.fetchall()
        conn.close()
        return results

# Initialize the bank system
bank = BankSystem()

# API Endpoints
@app.post("/accounts", response_model=dict, summary="Create a new bank account")
async def create_account(request: CreateAccountRequest):
    """Create a new bank account with the specified details."""
    success = bank.create_account(request.account_number, request.account_holder, request.initial_balance)
    if success:
        return {"message": f"Account {request.account_number} created successfully", "status": "success"}
    else:
        raise HTTPException(status_code=400, detail="Account number already exists")

@app.get("/accounts/{account_number}", response_model=AccountResponse, summary="Get account details")
async def get_account(account_number: str):
    """Get details of a specific account by account number."""
    account = bank.get_account(account_number)
    if account:
        return AccountResponse(
            account_number=account[0],
            account_holder=account[1],
            balance=float(account[2]),
            created_at=account[3]
        )
    else:
        raise HTTPException(status_code=404, detail="Account not found")

@app.get("/accounts", response_model=List[AccountResponse], summary="Get all accounts")
async def get_all_accounts():
    """Get a list of all bank accounts."""
    accounts = bank.get_all_accounts()
    return [
        AccountResponse(
            account_number=acc[0],
            account_holder=acc[1],
            balance=float(acc[2]),
            created_at=acc[3]
        ) for acc in accounts
    ]

# FIXED: Using DepositWithdrawRequest instead of TransactionRequest
@app.post("/accounts/{account_number}/deposit", response_model=dict, summary="Deposit money to account")
async def deposit(account_number: str, request: DepositWithdrawRequest):
    """Deposit money to the specified account."""
    # Validate account exists first
    account = bank.get_account(account_number)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    success = bank.deposit(account_number, request.amount, request.description or "Deposit")
    if success:
        updated_account = bank.get_account(account_number)
        return {
            "message": f"Successfully deposited ${request.amount:.2f}",
            "new_balance": float(updated_account[2]),
            "status": "success"
        }
    else:
        raise HTTPException(status_code=400, detail="Deposit failed")

# FIXED: Using DepositWithdrawRequest instead of TransactionRequest
@app.post("/accounts/{account_number}/withdraw", response_model=dict, summary="Withdraw money from account")
async def withdraw(account_number: str, request: DepositWithdrawRequest):
    """Withdraw money from the specified account."""
    # Validate account exists first
    account = bank.get_account(account_number)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    success = bank.withdraw(account_number, request.amount, request.description or "Withdrawal")
    if success:
        updated_account = bank.get_account(account_number)
        return {
            "message": f"Successfully withdrew ${request.amount:.2f}",
            "new_balance": float(updated_account[2]),
            "status": "success"
        }
    else:
        # Check if it's insufficient funds
        current_balance = float(account[2])
        if current_balance < request.amount:
            raise HTTPException(status_code=400, detail=f"Insufficient funds. Current balance: ${current_balance:.2f}")
        else:
            raise HTTPException(status_code=400, detail="Withdrawal failed")

@app.post("/transfer", response_model=dict, summary="Transfer money between accounts")
async def transfer(request: TransferRequest):
    """Transfer money from one account to another."""
    if request.from_account == request.to_account:
        raise HTTPException(status_code=400, detail="Cannot transfer to the same account")
    
    # Check if both accounts exist
    from_account = bank.get_account(request.from_account)
    to_account = bank.get_account(request.to_account)
    
    if not from_account:
        raise HTTPException(status_code=404, detail=f"Source account {request.from_account} not found")
    if not to_account:
        raise HTTPException(status_code=404, detail=f"Destination account {request.to_account} not found")
    
    success = bank.transfer(request.from_account, request.to_account, request.amount, request.description)
    if success:
        updated_from = bank.get_account(request.from_account)
        updated_to = bank.get_account(request.to_account)
        return {
            "message": f"Successfully transferred ${request.amount:.2f} from {request.from_account} to {request.to_account}",
            "from_account_balance": float(updated_from[2]),
            "to_account_balance": float(updated_to[2]),
            "status": "success"
        }
    else:
        # Check if it's insufficient funds
        current_balance = float(from_account[2])
        if current_balance < request.amount:
            raise HTTPException(status_code=400, detail=f"Insufficient funds in source account. Current balance: ${current_balance:.2f}")
        else:
            raise HTTPException(status_code=400, detail="Transfer failed")

@app.get("/accounts/{account_number}/transactions", response_model=List[TransactionResponse], summary="Get transaction history")
async def get_transaction_history(account_number: str, limit: int = 10):
    """Get transaction history for a specific account."""
    account = bank.get_account(account_number)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    transactions = bank.get_transaction_history(account_number, limit)
    return [
        TransactionResponse(
            transaction_type=trans[0],
            amount=float(trans[1]),
            from_account=trans[2],
            to_account=trans[3],
            description=trans[4] or "",
            timestamp=trans[5]
        ) for trans in transactions
    ]

@app.get("/accounts/{account_number}/balance", response_model=dict, summary="Get account balance")
async def get_balance(account_number: str):
    """Get the current balance of a specific account."""
    account = bank.get_account(account_number)
    if account:
        return {
            "account_number": account_number,
            "balance": float(account[2]),
            "status": "success"
        }
    else:
        raise HTTPException(status_code=404, detail="Account not found")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)