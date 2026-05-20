# Frontend Patterns

# Approved Stack

- React
- Vite
- TypeScript
- TailwindCSS

---

# Folder Structure

frontend/src/
├── components/
├── pages/
├── layouts/
├── hooks/
├── services/
├── store/
├── types/
├── utils/

---

# Component Principles

Components should:
- be reusable
- remain small
- have single responsibility

Avoid large monolithic components.

---

# State Management

Preferred:
- local state first
- React Query for server state
- Zustand if global state required

Avoid:
- Redux unless necessary

---

# API Integration

All API logic must live in:
- services/

Never call APIs directly from components.

---

# Styling Standards

Use:
- TailwindCSS

Avoid:
- inline styles
- duplicated CSS
- large CSS files

---

# Forms

Preferred:
- React Hook Form
- Zod validation

---

# Error Handling

All pages must:
- handle loading states
- handle error states
- avoid blank screens

---

# Performance Standards

Required:
- lazy loading routes
- memoization where useful
- avoid unnecessary renders

---

# Accessibility

Required:
- semantic HTML
- keyboard navigation
- aria labels where appropriate

---

# Authentication

Use:
- JWT authentication
- refresh token flow

Avoid storing tokens in localStorage where possible.

---

# Frontend Testing

Preferred:
- Vitest
- React Testing Library

Minimum:
- page rendering tests
- form validation tests