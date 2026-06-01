# Expense Tracker App

**Product:** Expense Tracker  
**Status:** UNDER_REVIEW  
**Priority:** MEDIUM  

## Summary

Expense Tracker App

## Details

# Simple Expense Tracker App – Requirements Document

## 1. Overview

### Product Name

Simple Expense Tracker

### Purpose

A lightweight Android application that helps users track their wallet balance by recording income and expenses. The app should be fast, simple, and require minimal setup.

### Target Users

* Individuals managing personal finances
* Students
* Freelancers
* Anyone needing a basic wallet balance tracker

---

## 2. Core Features

### 2.1 Wallet Balance Display

#### Description

The home screen displays the current wallet balance.

#### Requirements

* Show balance prominently at the top of the screen.
* Balance updates automatically when income or expenses are added.
* Display selected currency symbol with the balance.
* Example:

  * ₹5,250.00
  * $120.50
  * €300.00

---

### 2.2 Add Money (+)

#### Description

Users can add income or funds to their wallet.

#### Requirements

* Floating Action Button (FAB) or "+" button.
* On tap, open Add Money screen/dialog.
* User enters:

  * Amount (required)
  * Note (optional)
  * Date (default = current date)

#### Validation

* Amount must be greater than 0.

#### Result

* Wallet balance increases by entered amount.
* Transaction saved in history.

---

### 2.3 Add Expense (-)

#### Description

Users can record expenses.

#### Requirements

* Floating Action Button (FAB) or "-" button.
* On tap, open Add Expense screen/dialog.
* User enters:

  * Amount (required)
  * Note (optional)
  * Date (default = current date)

#### Validation

* Amount must be greater than 0.

#### Result

* Wallet balance decreases by entered amount.
* Transaction saved in history.

---

### 2.4 Currency Selection

#### Description

Users can choose their preferred currency.

#### Requirements

* Available from Settings screen.
* Provide dropdown/list of common currencies:

  * INR (₹)
  * USD ($)
  * EUR (€)
  * GBP (£)
  * AED (د.إ)
  * CAD ($)
  * AUD ($)

#### Result

* Selected currency is displayed throughout the app.
* Existing balance and transactions use the selected currency symbol.

---

### 2.5 Transaction History

#### Description

Display all wallet activities.

#### Requirements

* List transactions in reverse chronological order.
* Each transaction shows:

  * Type (Income/Expense)
  * Amount
  * Date
  * Note

#### Visual Indicators

* Income: "+"
* Expense: "-"

---

## 3. User Interface

### Home Screen

Components:

1. App Header
2. Current Wallet Balance
3. Currency Indicator
4. Recent Transactions List
5. Add Money (+) Button
6. Add Expense (-) Button

### Layout Example

Wallet Balance

₹5,250.00

[ + Add Money ] [ - Add Expense ]

Recent Transactions

* ₹1,000 Salary

- ₹250 Food
- ₹500 Transport

---

## 4. Data Storage

### Local Storage

Use Room Database or SQLite.

### Transaction Table

Fields:

* id
* type (Income/Expense)
* amount
* note
* date
* createdAt

### Settings Table

Fields:

* selectedCurrency
* currentBalance

---

## 5. Functional Requirements

### FR-01

System shall display current wallet balance.

### FR-02

System shall allow users to add money.

### FR-03

System shall allow users to add expenses.

### FR-04

System shall automatically recalculate wallet balance.

### FR-05

System shall store transaction history locally.

### FR-06

System shall allow currency selection.

### FR-07

System shall display all transactions in chronological order.

---

## 6. Non-Functional Requirements

### Performance

* App launch time under 2 seconds.
* Balance update should be instantaneous.

### Usability

* User should be able to add income or expense within 2 taps.

### Reliability

* Data persists after app restart.

### Offline Support

* Fully functional without internet connection.

---

## 7. Future Enhancements

### Version 2

* Categories (Food, Transport, Shopping)
* Monthly reports
* Charts and analytics
* Export to PDF/Excel
* Cloud backup
* Multiple wallets/accounts
* Budget tracking

---

## 8. Success Criteria

* User can view current wallet balance.
* User can add income and expenses.
* Balance updates correctly.
* User can select preferred currency.
* Transactions are stored and displayed successfully.
