import { describe, it, expect } from 'vitest'
import { OWNER_NAME, OWNER_LINKEDIN, OWNER_EMAIL, OWNER_GITHUB, validateOwnership } from '../ownership'

describe('ownership', () => {
  it('exports the default owner name', () => {
    expect(OWNER_NAME).toBe('AI Cloud Cost Detective')
  })

  it('exports empty LinkedIn URL by default (set via VITE_OWNER_LINKEDIN)', () => {
    expect(OWNER_LINKEDIN).toBe('')
  })

  it('exports empty email by default (set via VITE_OWNER_EMAIL)', () => {
    expect(OWNER_EMAIL).toBe('')
  })

  it('exports empty GitHub URL by default (set via VITE_OWNER_GITHUB)', () => {
    expect(OWNER_GITHUB).toBe('')
  })

  it('validateOwnership resolves without throwing', async () => {
    await expect(validateOwnership()).resolves.toBeUndefined()
  })
})
