import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Building2, Plus, Settings, Users, Mail, Trash2, RefreshCw,
  AlertTriangle, ChevronRight, UserPlus, LogOut, X, Send,
} from 'lucide-react'
import { teams as teamsApi } from '../api'
import type { Organization, Member, Invitation } from '../types'

type Tab = 'members' | 'invitations' | 'settings'

const ROLE_COLORS: Record<string, string> = {
  owner: '#f59e0b',
  admin: '#3b82f6',
  member: '#10b981',
  viewer: '#6b7280',
}

const ROLE_OPTIONS = [
  { value: 'admin', label: 'Admin' },
  { value: 'member', label: 'Member' },
  { value: 'viewer', label: 'Viewer' },
]

function fmt(iso: string) {
  if (!iso) return '—'
  const d = new Date(iso)
  return isNaN(d.getTime()) ? '—' : d.toLocaleString(undefined, { dateStyle: 'medium' })
}

export default function Teams() {
  const navigate = useNavigate()

  const [orgs, setOrgs] = useState<Organization[]>([])
  const [loadingOrgs, setLoadingOrgs] = useState(true)
  const [orgError, setOrgError] = useState('')

  const [selectedOrg, setSelectedOrg] = useState<Organization | null>(null)
  const [tab, setTab] = useState<Tab>('members')

  const [members, setMembers] = useState<Member[]>([])
  const [loadingMembers, setLoadingMembers] = useState(false)
  const [memberError, setMemberError] = useState('')

  const [invitations, setInvitations] = useState<Invitation[]>([])
  const [loadingInvites, setLoadingInvites] = useState(false)

  // Create org
  const [showCreate, setShowCreate] = useState(false)
  const [newOrgName, setNewOrgName] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState('')

  // Rename org
  const [renameValue, setRenameValue] = useState('')
  const [renaming, setRenaming] = useState(false)
  const [renameError, setRenameError] = useState('')

  // Delete org
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)

  // Add member
  const [showAddMember, setShowAddMember] = useState(false)
  const [newMemberId, setNewMemberId] = useState('')
  const [newMemberRole, setNewMemberRole] = useState('member')
  const [addingMember, setAddingMember] = useState(false)
  const [addMemberError, setAddMemberError] = useState('')

  // Invite
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState('member')
  const [sendingInvite, setSendingInvite] = useState(false)
  const [inviteError, setInviteError] = useState('')

  // Change role
  const [changingRole, setChangingRole] = useState<{ orgId: number; userId: number; role: string } | null>(null)

  // Remove member
  const [removingMember, setRemovingMember] = useState<number | null>(null)

  const loadOrgs = useCallback(() => {
    setLoadingOrgs(true)
    setOrgError('')
    teamsApi.list()
      .then(setOrgs)
      .catch((e) => setOrgError(e.message))
      .finally(() => setLoadingOrgs(false))
  }, [])

  useEffect(() => { loadOrgs() }, [loadOrgs])

  const loadMembers = useCallback(async (orgId: number) => {
    setLoadingMembers(true)
    setMemberError('')
    try {
      const m = await teamsApi.members.list(orgId)
      setMembers(m)
    } catch (e: unknown) {
      setMemberError(e instanceof Error ? e.message : 'Failed to load members')
    } finally {
      setLoadingMembers(false)
    }
  }, [])

  const loadInvitations = useCallback(async (orgId: number) => {
    setLoadingInvites(true)
    try {
      const invs = await teamsApi.invitations.list(orgId)
      setInvitations(invs)
    } catch { /* ignore */ }
    finally { setLoadingInvites(false) }
  }, [])

  const handleSelectOrg = (org: Organization) => {
    setSelectedOrg(org)
    setTab('members')
    setRenameValue(org.name)
    setConfirmDelete(false)
    loadMembers(org.id)
    loadInvitations(org.id)
  }

  const handleCreate = async () => {
    if (!newOrgName.trim() || creating) return
    setCreateError('')
    setCreating(true)
    try {
      const org = await teamsApi.create(newOrgName.trim())
      setOrgs((prev) => [org, ...prev])
      setShowCreate(false)
      setNewOrgName('')
      handleSelectOrg(org)
    } catch (e: unknown) {
      setCreateError(e instanceof Error ? e.message : 'Failed to create organization')
    } finally {
      setCreating(false)
    }
  }

  const handleRename = async () => {
    if (!selectedOrg || !renameValue.trim() || renaming) return
    setRenameError('')
    setRenaming(true)
    try {
      const updated = await teamsApi.update(selectedOrg.id, renameValue.trim())
      setOrgs((prev) => prev.map((o) => o.id === updated.id ? updated : o))
      setSelectedOrg(updated)
    } catch (e: unknown) {
      setRenameError(e instanceof Error ? e.message : 'Failed to rename')
    } finally {
      setRenaming(false)
    }
  }

  const handleDelete = async () => {
    if (!selectedOrg || deleting) return
    setDeleting(true)
    try {
      await teamsApi.delete(selectedOrg.id)
      setOrgs((prev) => prev.filter((o) => o.id !== selectedOrg.id))
      setSelectedOrg(null)
      setConfirmDelete(false)
    } catch { /* ignore */ }
    finally { setDeleting(false) }
  }

  const handleAddMember = async () => {
    if (!selectedOrg || !newMemberId.trim() || addingMember) return
    const uid = parseInt(newMemberId.trim(), 10)
    if (isNaN(uid)) { setAddMemberError('Enter a valid user ID'); return }
    setAddMemberError('')
    setAddingMember(true)
    try {
      await teamsApi.members.add(selectedOrg.id, uid, newMemberRole)
      setNewMemberId('')
      setShowAddMember(false)
      loadMembers(selectedOrg.id)
    } catch (e: unknown) {
      setAddMemberError(e instanceof Error ? e.message : 'Failed to add member')
    } finally {
      setAddingMember(false)
    }
  }

  const handleChangeRole = async (userId: number, role: string) => {
    if (!selectedOrg || changingRole) return
    setChangingRole({ orgId: selectedOrg.id, userId, role })
    try {
      await teamsApi.members.updateRole(selectedOrg.id, userId, role)
      loadMembers(selectedOrg.id)
    } catch { /* ignore */ }
    finally { setChangingRole(null) }
  }

  const handleRemoveMember = async (userId: number) => {
    if (!selectedOrg || removingMember !== null) return
    setRemovingMember(userId)
    try {
      await teamsApi.members.remove(selectedOrg.id, userId)
      loadMembers(selectedOrg.id)
    } catch { /* ignore */ }
    finally { setRemovingMember(null) }
  }

  const handleInvite = async () => {
    if (!selectedOrg || !inviteEmail.trim() || sendingInvite) return
    setInviteError('')
    setSendingInvite(true)
    try {
      await teamsApi.invitations.create(selectedOrg.id, inviteEmail.trim(), inviteRole)
      setInviteEmail('')
      loadInvitations(selectedOrg.id)
    } catch (e: unknown) {
      setInviteError(e instanceof Error ? e.message : 'Failed to send invitation')
    } finally {
      setSendingInvite(false)
    }
  }

  const currentRole = selectedOrg
    ? members.find((m) => m.user_id === (orgs.length > 0 ? undefined : undefined))?.role
    : null

  const canManage = selectedOrg
    ? members.some((m) => m.role === 'owner' || m.role === 'admin')
    : false

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Teams</h1>
          <p className="text-sm mt-0.5" style={{ color: 'var(--color-text-secondary)' }}>
            Manage organizations, members, and roles
          </p>
        </div>
        <button onClick={() => { setShowCreate(true); setCreateError('') }}
          className="btn-primary flex items-center gap-1.5 text-sm">
          <Plus size={15} /> Create Team
        </button>
      </div>

      {orgError && (
        <div className="card flex items-center gap-3 text-red-400 mb-4">
          <AlertTriangle size={16} /> {orgError}
        </div>
      )}

      {/* Create Org Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setShowCreate(false)}>
          <div className="card max-w-md w-full mx-4 p-5 space-y-4" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-white">Create Organization</h2>
              <button onClick={() => setShowCreate(false)} style={{ color: 'var(--color-text-tertiary)' }}>
                <X size={16} />
              </button>
            </div>
            <input className="input w-full text-sm" placeholder="Organization name"
              value={newOrgName} onChange={(e) => setNewOrgName(e.target.value)}
              autoFocus onKeyDown={(e) => e.key === 'Enter' && handleCreate()} />
            {createError && <p className="text-red-400 text-xs">{createError}</p>}
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowCreate(false)} className="btn-ghost text-sm">Cancel</button>
              <button onClick={handleCreate} disabled={!newOrgName.trim() || creating}
                className="btn-primary text-sm flex items-center gap-1">
                {creating && <RefreshCw size={12} className="animate-spin" />}
                {creating ? 'Creating…' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main layout */}
      <div className="flex gap-4" style={{ minHeight: '480px' }}>
        {/* Left: Org list */}
        <div className="w-72 shrink-0 space-y-2">
          {loadingOrgs ? (
            <div className="space-y-2">
              {[1, 2].map((n) => (
                <div key={n} className="card" style={{ padding: '14px 16px' }}>
                  <div className="h-4 rounded w-32" style={{ background: 'var(--color-section-bg)' }} />
                  <div className="h-3 rounded w-20 mt-2" style={{ background: 'var(--color-section-bg)' }} />
                </div>
              ))}
            </div>
          ) : orgs.length === 0 ? (
            <div className="card text-center py-8" style={{ color: 'var(--color-text-tertiary)' }}>
              <Building2 size={28} className="mx-auto mb-2 opacity-40" />
              <p className="text-xs">No teams yet</p>
              <button onClick={() => setShowCreate(true)} className="btn-ghost text-xs mt-2">Create one</button>
            </div>
          ) : (
            orgs.map((org) => {
              const sel = selectedOrg?.id === org.id
              return (
                <div key={org.id} role="button" tabIndex={0}
                  className="card cursor-pointer transition-all"
                  style={{
                    padding: '14px 16px',
                    borderColor: sel ? 'var(--color-accent)' : undefined,
                  }}
                  onClick={() => handleSelectOrg(org)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSelectOrg(org)}>
                  <div className="flex items-center justify-between">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-white truncate">{org.name}</p>
                      <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-tertiary)' }}>
                        Created {fmt(org.created_at)}
                      </p>
                    </div>
                    <ChevronRight size={14} style={{
                      color: sel ? 'var(--color-accent)' : 'var(--color-text-tertiary)',
                      transform: sel ? 'translateX(2px)' : undefined,
                      transition: 'transform 0.15s',
                    }} />
                  </div>
                </div>
              )
            })
          )}
        </div>

        {/* Right: Detail panel */}
        <div className="flex-1 min-w-0">
          {!selectedOrg ? (
            <div className="card text-center py-16" style={{ color: 'var(--color-text-tertiary)' }}>
              <Building2 size={40} className="mx-auto mb-3 opacity-30" />
              <p className="font-semibold text-white/60">Select a team</p>
              <p className="text-xs mt-1">Choose a team from the left to view and manage its members.</p>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Org header */}
              <div className="card" style={{ padding: '18px 20px' }}>
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-lg font-bold text-white">{selectedOrg.name}</h2>
                    <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-tertiary)' }}>
                      ID: {selectedOrg.id} · Created {fmt(selectedOrg.created_at)}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button onClick={() => { loadMembers(selectedOrg.id); loadInvitations(selectedOrg.id) }}
                      className="btn-ghost text-xs flex items-center gap-1">
                      <RefreshCw size={12} /> Refresh
                    </button>
                  </div>
                </div>
              </div>

              {/* Tabs */}
              <div className="flex gap-1 border-b" style={{ borderColor: 'var(--color-section-border)' }}>
                {[
                  { id: 'members' as Tab, Icon: Users, label: 'Members' },
                  { id: 'invitations' as Tab, Icon: Mail, label: 'Invitations' },
                  { id: 'settings' as Tab, Icon: Settings, label: 'Settings' },
                ].map(({ id, Icon, label }) => (
                  <button key={id} onClick={() => setTab(id)}
                    className="flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-all"
                    style={{
                      borderBottom: tab === id ? '2px solid var(--color-accent)' : '2px solid transparent',
                      color: tab === id ? 'var(--color-accent)' : 'var(--color-text-tertiary)',
                    }}>
                    <Icon size={14} />
                    {label}
                  </button>
                ))}
              </div>

              {/* ── Members Tab ── */}
              {tab === 'members' && (
                <div className="space-y-3">
                  {canManage && (
                    <div className="flex justify-end">
                      <button onClick={() => { setShowAddMember(true); setAddMemberError('') }}
                        className="btn-ghost text-xs flex items-center gap-1">
                        <UserPlus size={13} /> Add Member
                      </button>
                    </div>
                  )}

                  {showAddMember && (
                    <div className="card" style={{ padding: '14px 16px', borderColor: 'rgba(59,130,246,0.4)' }}>
                      <div className="flex items-end gap-2">
                        <div className="flex-1">
                          <label className="block text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>
                            User ID
                          </label>
                          <input className="input w-full text-sm" placeholder="Enter user ID"
                            value={newMemberId} onChange={(e) => setNewMemberId(e.target.value)}
                            autoFocus />
                        </div>
                        <div>
                          <label className="block text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>
                            Role
                          </label>
                          <select className="input text-sm" value={newMemberRole}
                            onChange={(e) => setNewMemberRole(e.target.value)}
                            style={{ background: 'var(--color-select-bg)', color: 'var(--color-select-text)' }}>
                            {ROLE_OPTIONS.map((r) => (
                              <option key={r.value} value={r.value}>{r.label}</option>
                            ))}
                          </select>
                        </div>
                        <button onClick={handleAddMember} disabled={!newMemberId.trim() || addingMember}
                          className="btn-primary text-xs px-3 py-2 flex items-center gap-1">
                          {addingMember ? <RefreshCw size={11} className="animate-spin" /> : <UserPlus size={13} />}
                          Add
                        </button>
                      </div>
                      {addMemberError && <p className="text-red-400 text-xs mt-2">{addMemberError}</p>}
                    </div>
                  )}

                  {memberError && (
                    <div className="flex items-center gap-2 text-red-400 text-xs">
                      <AlertTriangle size={12} /> {memberError}
                    </div>
                  )}

                  {loadingMembers ? (
                    <div className="space-y-2">
                      {[1, 2, 3].map((n) => (
                        <div key={n} className="card" style={{ padding: '14px 16px' }}>
                          <div className="h-4 rounded w-40" style={{ background: 'var(--color-section-bg)' }} />
                          <div className="h-3 rounded w-24 mt-2" style={{ background: 'var(--color-section-bg)' }} />
                        </div>
                      ))}
                    </div>
                  ) : members.length === 0 ? (
                    <div className="card text-center py-8" style={{ color: 'var(--color-text-tertiary)' }}>
                      <Users size={24} className="mx-auto mb-2 opacity-40" />
                      <p className="text-xs">No members yet</p>
                    </div>
                  ) : (
                    <div className="space-y-1.5">
                      {members.map((m) => {
                        const isOwner = m.role === 'owner'
                        const canEdit = canManage && !isOwner
                        const isChanging = changingRole?.orgId === selectedOrg.id && changingRole?.userId === m.user_id
                        return (
                          <div key={m.id} className="card"
                            style={{ padding: '12px 16px', display: 'flex', alignItems: 'center', gap: '12px' }}>
                            <div style={{
                              width: '32px', height: '32px', borderRadius: '50%',
                              background: `${ROLE_COLORS[m.role] || '#6b7280'}20`,
                              border: `1px solid ${ROLE_COLORS[m.role] || '#6b7280'}40`,
                              display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                            }}>
                              <span className="text-xs font-bold" style={{ color: ROLE_COLORS[m.role] || '#6b7280' }}>
                                {m.email.charAt(0).toUpperCase()}
                              </span>
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-white truncate">{m.email}</p>
                              <p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
                                ID: {m.user_id}
                              </p>
                            </div>
                            {canEdit ? (
                              <select value={m.role}
                                onChange={(e) => handleChangeRole(m.user_id, e.target.value)}
                                disabled={isChanging}
                                className="text-xs px-2 py-1 rounded-lg"
                                style={{
                                  background: `${ROLE_COLORS[m.role]}20`,
                                  color: ROLE_COLORS[m.role],
                                  border: `1px solid ${ROLE_COLORS[m.role]}40`,
                                  cursor: 'pointer',
                                }}>
                                {ROLE_OPTIONS.map((r) => (
                                  <option key={r.value} value={r.value}>{r.label}</option>
                                ))}
                              </select>
                            ) : (
                              <span className="text-xs px-2 py-1 rounded-lg font-medium"
                                style={{
                                  background: `${ROLE_COLORS[m.role]}20`,
                                  color: ROLE_COLORS[m.role],
                                  border: `1px solid ${ROLE_COLORS[m.role]}40`,
                                }}>
                                {m.role}
                              </span>
                            )}
                            {canEdit && (
                              <button onClick={() => handleRemoveMember(m.user_id)}
                                disabled={removingMember === m.user_id}
                                className="p-1.5 rounded-lg transition-colors hover:bg-red-500/10"
                                style={{ color: removingMember === m.user_id ? 'var(--color-text-tertiary)' : '#ef4444' }}>
                                {removingMember === m.user_id
                                  ? <RefreshCw size={13} className="animate-spin" />
                                  : <LogOut size={13} />}
                              </button>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              )}

              {/* ── Invitations Tab ── */}
              {tab === 'invitations' && (
                <div className="space-y-4">
                  {canManage && (
                    <div className="card" style={{ padding: '16px', borderColor: 'rgba(139,92,246,0.3)' }}>
                      <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-1.5">
                        <Send size={13} /> Send Invitation
                      </h3>
                      <div className="flex items-end gap-2">
                        <div className="flex-1">
                          <label className="block text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>
                            Email address
                          </label>
                          <input className="input w-full text-sm" placeholder="colleague@company.com"
                            value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)}
                            autoFocus />
                        </div>
                        <div>
                          <label className="block text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>
                            Role
                          </label>
                          <select className="input text-sm" value={inviteRole}
                            onChange={(e) => setInviteRole(e.target.value)}
                            style={{ background: 'var(--color-select-bg)', color: 'var(--color-select-text)' }}>
                            {ROLE_OPTIONS.map((r) => (
                              <option key={r.value} value={r.value}>{r.label}</option>
                            ))}
                          </select>
                        </div>
                        <button onClick={handleInvite} disabled={!inviteEmail.trim() || sendingInvite}
                          className="btn-primary text-xs px-3 py-2 flex items-center gap-1">
                          {sendingInvite ? <RefreshCw size={11} className="animate-spin" /> : <Send size={12} />}
                          Send
                        </button>
                      </div>
                      {inviteError && <p className="text-red-400 text-xs mt-2">{inviteError}</p>}
                    </div>
                  )}

                  {loadingInvites ? (
                    <div className="space-y-2">
                      {[1, 2].map((n) => (
                        <div key={n} className="card" style={{ padding: '14px 16px' }}>
                          <div className="h-4 rounded w-48" style={{ background: 'var(--color-section-bg)' }} />
                        </div>
                      ))}
                    </div>
                  ) : invitations.length === 0 ? (
                    <div className="card text-center py-8" style={{ color: 'var(--color-text-tertiary)' }}>
                      <Mail size={24} className="mx-auto mb-2 opacity-40" />
                      <p className="text-xs">No pending invitations</p>
                    </div>
                  ) : (
                    <div className="space-y-1.5">
                      {invitations.map((inv) => {
                        const expired = new Date(inv.expires_at) < new Date()
                        return (
                          <div key={inv.id} className="card"
                            style={{
                              padding: '12px 16px', display: 'flex', alignItems: 'center', gap: '12px',
                              opacity: inv.accepted || expired ? 0.5 : 1,
                            }}>
                            <Mail size={14} style={{ color: 'var(--color-text-tertiary)', flexShrink: 0 }} />
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-white truncate">{inv.email}</p>
                              <p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
                                Role: {inv.role} · Expires {fmt(inv.expires_at)}
                              </p>
                            </div>
                            <span className="text-xs px-2 py-0.5 rounded-full font-medium"
                              style={{
                                background: inv.accepted
                                  ? 'rgba(16,185,129,0.15)' : expired
                                    ? 'rgba(239,68,68,0.15)' : 'rgba(59,130,246,0.15)',
                                color: inv.accepted
                                  ? '#10b981' : expired
                                    ? '#ef4444' : '#3b82f6',
                                border: `1px solid ${inv.accepted ? 'rgba(16,185,129,0.4)' : expired ? 'rgba(239,68,68,0.4)' : 'rgba(59,130,246,0.4)'}`,
                              }}>
                              {inv.accepted ? 'Accepted' : expired ? 'Expired' : 'Pending'}
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              )}

              {/* ── Settings Tab ── */}
              {tab === 'settings' && (
                <div className="space-y-4">
                  {/* Rename */}
                  <div className="card" style={{ padding: '16px' }}>
                    <h3 className="text-sm font-semibold text-white mb-3">Team Name</h3>
                    <div className="flex items-end gap-2">
                      <div className="flex-1">
                        <input className="input w-full text-sm"
                          value={renameValue} onChange={(e) => setRenameValue(e.target.value)} />
                      </div>
                      <button onClick={handleRename} disabled={!renameValue.trim() || renaming}
                        className="btn-primary text-sm flex items-center gap-1">
                        {renaming && <RefreshCw size={12} className="animate-spin" />}
                        Rename
                      </button>
                    </div>
                    {renameError && <p className="text-red-400 text-xs mt-2">{renameError}</p>}
                  </div>

                  {/* Delete */}
                  <div className="card" style={{ padding: '16px', borderColor: 'rgba(239,68,68,0.3)' }}>
                    <h3 className="text-sm font-semibold text-red-400 mb-1">Danger Zone</h3>
                    <p className="text-xs mb-3" style={{ color: 'var(--color-text-tertiary)' }}>
                      Permanently delete this organization and all its data. This action cannot be undone.
                    </p>
                    {!confirmDelete ? (
                      <button onClick={() => setConfirmDelete(true)}
                        className="btn-ghost text-xs flex items-center gap-1" style={{ color: '#ef4444' }}>
                        <Trash2 size={12} /> Delete Organization
                      </button>
                    ) : (
                      <div className="flex items-center gap-2">
                        <button onClick={handleDelete} disabled={deleting}
                          className="btn-primary text-xs flex items-center gap-1"
                          style={{ background: '#dc2626' }}>
                          {deleting ? <RefreshCw size={11} className="animate-spin" /> : <Trash2 size={12} />}
                          {deleting ? 'Deleting…' : 'Confirm Delete'}
                        </button>
                        <button onClick={() => setConfirmDelete(false)}
                          className="btn-ghost text-xs">Cancel</button>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
