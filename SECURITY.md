# Security Policy

## Reporting Vulnerabilities

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT** open public GitHub issues for security bugs
2. Email: [security@yourdomain.com]
3. Include: Description, steps to reproduce, potential impact
4. Allow 90 days for response before public disclosure

## Security Measures

### Authentication

- JWT tokens stored in httpOnly cookies (not accessible to JavaScript)
- Passwords hashed with bcrypt (12 rounds)
- Token expiration: 8 hours
- Token revocation on logout

### Data Protection

- Cloud credentials **never stored** - memory only during scans
- All database connections encrypted
- Environment variables for sensitive configuration
- No secrets in codebase (enforced by .gitignore)

### Rate Limiting

| Endpoint | Limit |
|----------|-------|
| Login | 20 requests/minute per IP |
| Signup | 10 requests/5 minutes per IP |
| Scan | 5 concurrent per platform, 3 per user |
| Validate | 10 requests/minute per user |

### Network Security

- CORS restricted to configured origins
- Security headers (HSTS, CSP, X-Frame-Options)
- Backend not exposed to internet (only via ALB)
- Database in private subnet

## Dependencies

Regular security audits are performed on dependencies:
- `pip audit` for Python packages
- `npm audit` for Node.js packages
- Dependabot alerts enabled

## Configuration

### Environment Variables

All secrets must be provided via environment variables:

```bash
# Required
POSTGRES_PASSWORD=secure-password

# Optional AI keys
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

### Never Commit

- `.env` files
- API keys or tokens
- Database credentials
- SSL certificates
- Service account keys

## Compliance

This project follows:
- OWASP Top 10 guidelines
- AWS Well-Architected Framework
- CIS Benchmarks (where applicable)

## Updates

Security patches are released as soon as vulnerabilities are confirmed. Watch the repository for security advisories.
