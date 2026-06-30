import { describe, it, expect } from 'vitest'
import { OWNER_NAME, OWNER_LINKEDIN, OWNER_EMAIL, OWNER_GITHUB, validateOwnership } from '../ownership'

describe('ownership', () => {
  it('exports the owner name', () => {
    expect(OWNER_NAME).toBe('AI-CostMonitoring-Reporting')
  })

  it('exports the LinkedIn URL', () => {
    expect(OWNER_LINKEDIN).toBe('www.linkedin.com/in/ashok-kunchala-127820217')
  })

  it('exports the email', () => {
    expect(OWNER_EMAIL).toBe('ashokkunchla@gmail.com')
  })

  it('exports the GitHub URL', () => {
    expect(OWNER_GITHUB).toBe('github.com/Ashokkunchala')
  })

  it('validateOwnership resolves without throwing', async () => {
    await expect(validateOwnership()).resolves.toBeUndefined()
  })
})
