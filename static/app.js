// ─── SPA Router & State Manager ──────────────────────────────────────────────
class NorwemaApp {
    constructor() {
        this.state = {
            page: 'home',
            isAdmin: sessionStorage.getItem('adminToken') !== null,
            events: [],
            blogs: [],
            registrations: [],
            config: {
                api_key: '',
                has_key: false,
                selected_model: 'models/gemini-2.5-flash',
                mock_agent: true,
                is_offline: true
            },
            logs: [],
            // Registration wizard details
            regEvent: null,
            regStep: 1,
            regData: {}
        };

        // DOM elements
        this.mount = document.getElementById('content-mount');
        
        // Bind UI Events
        this.initEvents();
    }

    // Initialize Event Listeners
    initEvents() {
        // Nav Toggle (Hamburger menu for mobile)
        const navToggle = document.getElementById('navToggle');
        const navMenu = document.getElementById('navMenu');
        
        if (navToggle) {
            navToggle.addEventListener('click', () => {
                navToggle.classList.toggle('open');
                navMenu.classList.toggle('open');
            });
        }

        // Navigation Links click routing
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const page = link.getAttribute('data-page');
                if (page) {
                    this.navigate(page);
                    // Close mobile menu if open
                    if (navMenu.classList.contains('open')) {
                        navToggle.classList.remove('open');
                        navMenu.classList.remove('open');
                    }
                }
            });
        });

        // Admin Auth Buttons
        document.getElementById('btn-nav-login').addEventListener('click', (e) => {
            e.preventDefault();
            this.navigate('login');
        });

        document.getElementById('btn-nav-logout').addEventListener('click', (e) => {
            e.preventDefault();
            this.logout();
        });

        // Wizard Step 1 Submission
        document.getElementById('regFormStep1').addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleRegistrationStep1();
        });

        // Wizard Step 2 Submission
        document.getElementById('regFormStep2').addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleRegistrationStep2();
        });
    }

    // State routing
    async navigate(page) {
        // Auth gate
        if (['agents', 'builder', 'admin'].includes(page) && !this.state.isAdmin) {
            this.showToast('🔐 This section requires admin access.', 'warning');
            this.navigate('login');
            return;
        }

        this.state.page = page;
        this.updateNavUI();
        
        // Clear mount point and show spinner
        this.mount.innerHTML = `<div class="card" style="text-align:center;padding:40px;"><div class="bdot" style="width:20px;height:20px;margin:0 auto 10px;background:var(--saffron);"></div>Loading page content...</div>`;

        try {
            switch (page) {
                case 'home':
                    await this.fetchEvents();
                    await this.fetchConfig();
                    this.renderHome();
                    break;
                case 'stories':
                    await this.fetchBlogs();
                    this.renderStories();
                    break;
                case 'login':
                    if (this.state.isAdmin) {
                        this.navigate('admin');
                        return;
                    }
                    this.renderLogin();
                    break;
                case 'agents':
                    await this.fetchConfig();
                    this.renderAgentsPlayground();
                    break;
                case 'builder':
                    this.renderBuilderWorkspace();
                    break;
                case 'admin':
                    await this.fetchConfig();
                    await this.fetchEvents();
                    await this.fetchBlogs();
                    await this.fetchRegistrations();
                    this.renderSystemAdmin();
                    break;
            }
        } catch (error) {
            console.error(error);
            this.showToast('Failed to load data for page: ' + page, 'error');
            this.mount.innerHTML = `<div class="card" style="text-align:center;color:var(--maroon);padding:30px;"><h3>Error Loading Content</h3><p>${error.message}</p></div>`;
        }
    }

    // Refresh Navigation bar active states
    updateNavUI() {
        // Remove active class
        document.querySelectorAll('.nav-link').forEach(link => link.classList.remove('active'));
        
        // Set active to current
        const currentLink = document.getElementById(`btn-nav-${this.state.page}`);
        if (currentLink) currentLink.classList.add('active');

        // Toggle admin menu elements visibility
        const adminLinks = document.querySelectorAll('.admin-only');
        const loginBtn = document.getElementById('btn-nav-login');
        const logoutBtn = document.getElementById('btn-nav-logout');

        if (this.state.isAdmin) {
            adminLinks.forEach(link => link.style.display = 'block');
            if (loginBtn) loginBtn.style.display = 'none';
            if (logoutBtn) logoutBtn.style.display = 'block';
        } else {
            adminLinks.forEach(link => link.style.display = 'none');
            if (loginBtn) loginBtn.style.display = 'block';
            if (logoutBtn) logoutBtn.style.display = 'none';
        }
    }

    // HTTP fetch wrapper with authorization header & log collection
    async apiFetch(url, options = {}) {
        options.headers = options.headers || {};
        
        // Inject admin token if logged in
        if (this.state.isAdmin) {
            const token = sessionStorage.getItem('adminToken');
            if (token) {
                options.headers['X-Admin-Password'] = token;
            }
        }

        const response = await fetch(url, options);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.message || `API error (${response.status})`);
        }

        // Collect Firestore MCP JSON-RPC logs from response if present
        if (data.mcp_logs && Array.isArray(data.mcp_logs)) {
            this.state.logs = [...this.state.logs, ...data.mcp_logs];
            // Prune logs if too long (max 100)
            if (this.state.logs.length > 100) {
                this.state.logs = this.state.logs.slice(this.state.logs.length - 100);
            }
            this.updateTerminalConsole();
        }

        return data.result;
    }

    // ─── API Requests ────────────────────────────────────────────────────────
    async fetchEvents() {
        this.state.events = await this.apiFetch('/api/events');
    }

    async fetchBlogs() {
        this.state.blogs = await this.apiFetch('/api/blogs');
    }

    async fetchRegistrations() {
        this.state.registrations = await this.apiFetch('/api/registrations');
    }

    async fetchConfig() {
        this.state.config = await this.apiFetch('/api/config');
    }

    // ─── Authentications ─────────────────────────────────────────────────────
    async login(username, password) {
        try {
            const res = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            const data = await res.json();
            
            if (res.ok && data.status === 'success') {
                sessionStorage.setItem('adminToken', password);
                this.state.isAdmin = true;
                this.showToast('🔓 Access Granted. Welcome Admin!', 'success');
                this.navigate('admin');
            } else {
                this.showToast(data.message || 'Invalid credentials.', 'error');
            }
        } catch (error) {
            this.showToast('Login connection failed: ' + error.message, 'error');
        }
    }

    logout() {
        sessionStorage.removeItem('adminToken');
        this.state.isAdmin = false;
        this.showToast('🔐 Logged out successfully.', 'info');
        this.navigate('home');
    }

    // ─── Page Templates Renderers ────────────────────────────────────────────
    
    // 1. Home Page
    renderHome() {
        const eventsList = this.state.events || [];
        
        let eventsHtml = '';
        if (eventsList.length === 0) {
            eventsHtml = `<div class="card" style="padding:15px;color:var(--text-lt);font-style:italic;">No upcoming events scheduled. Check back soon!</div>`;
        } else {
            eventsHtml = eventsList.map(ev => {
                const schema = this.state.config.form_schemas && this.state.config.form_schemas[ev.title];
                const active = schema ? schema.active : false;
                const fee = schema ? schema.fee : 0;
                
                return `
                    <div class="event-card">
                        <div class="event-title">${ev.title}</div>
                        ${ev.date ? `<div class="event-date">📅 ${ev.date}</div>` : ''}
                        <div class="event-desc">${ev.description || ''}</div>
                        ${active ? `
                            <button class="btn btn-primary" style="margin-top:14px;" onclick="app.openRegistrationModal('${ev.title.replace(/'/g, "\\'")}', ${fee})">
                                🎟 Register &mdash; ${fee === 0 ? 'FREE' : `£${fee.toFixed(0)}/adult`}
                            </button>
                        ` : ''}
                    </div>
                `;
            }).join('');
        }

        this.mount.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;margin:12px 0 2px;flex-wrap:wrap;gap:10px;">
                <h2 style="font-size:1.6rem;color:var(--maroon);">North West Marathi Association</h2>
            </div>
            <div style="color:var(--text-lt);font-size:.87rem;font-style:italic;margin-bottom:6px;">
                नॉर्थ वेस्ट मराठी असोसिएशन &nbsp;·&nbsp; Preserving culture, building community since 1973
            </div>
            <div class="ornament">❋  ✦  ❋</div>
            
            <div class="home-grid">
                <div class="home-left">
                    <div class="sec-head">🎯 Our Objective</div>
                    <div class="card">
                        <p class="objective">
                            To promote, preserve and cultivate Maharashtrian culture and values within the
                            Marathi speaking community by organising cultural and social events for all ages
                            throughout the year.
                        </p>
                    </div>

                    <div class="sec-head">📜 Our History</div>
                    <div class="card">
                        <p style="line-height:1.85;">
                            Our roots trace back to <strong>1973 in Manchester</strong>, founded through the
                            <em>Marathi Doctors, Manchester (MDM)</em> initiative by the Ganpule family.
                            After 35 years of service, we formally became <strong>NORWEMA</strong>
                            in 2008 &mdash; expanding to unite all Marathi-speaking families across North West England.
                        </p>
                    </div>
                </div>
                <div class="home-right">
                    <div class="sec-head">🗓 Upcoming Events</div>
                    <div class="events-container">${eventsHtml}</div>
                </div>
            </div>
        `;
    }

    // 2. Stories / Blogs Page
    renderStories() {
        const blogsList = this.state.blogs || [];
        
        let blogsHtml = '';
        if (blogsList.length === 0) {
            blogsHtml = `<div class="card" style="padding:20px;text-align:center;color:var(--text-lt);">No stories published yet. An admin can publish one from the Admin Panel.</div>`;
        } else {
            blogsHtml = blogsList.map(blog => `
                <div class="story-card">
                    <div class="story-title">${blog.title}</div>
                    <div class="story-meta">
                        <span>✍️ ${blog.author || 'Cultural Blogger Agent'}</span>
                        <span>&nbsp;&middot;&nbsp;</span>
                        <span>📅 ${blog.date || ''}</span>
                    </div>
                    <div class="story-body">${blog.content}</div>
                </div>
            `).join('');
        }

        this.mount.innerHTML = `
            <div class="page-hero">
                <h2>📖 Past Stories &amp; Community Blogs</h2>
                <p>Memories, milestones and the voice of our Marathi community</p>
            </div>
            <div class="stories-container">${blogsHtml}</div>
        `;
    }

    // 3. Admin Login Page
    renderLogin() {
        this.mount.innerHTML = `
            <div class="login-container">
                <div class="login-header-card">
                    <div class="logo">
                        <img src="/norwema_logo_new.png" alt="NORWEMA Logo" class="login-logo-img" onerror="this.src='/norwema_logo.jpg'">
                    </div>
                    <h3>Admin Access</h3>
                    <p style="font-size:0.82rem;color:var(--text-lt);margin-top:4px;">Sign in to manage events, stories and AI agents</p>
                </div>
                <div class="login-form-card">
                    <form id="adminLoginForm">
                        <div class="form-group">
                            <label for="login-username">Username</label>
                            <input type="text" id="login-username" value="admin" required readonly style="background:#f4f4f4;">
                        </div>
                        <div class="form-group" style="margin-bottom:24px;">
                            <label for="login-password">Password</label>
                            <input type="password" id="login-password" required placeholder="••••••••••••" autofocus>
                        </div>
                        <button type="submit" class="btn btn-primary btn-full">Sign In</button>
                    </form>
                </div>
            </div>
        `;

        document.getElementById('adminLoginForm').addEventListener('submit', (e) => {
            e.preventDefault();
            const uname = document.getElementById('login-username').value;
            const pword = document.getElementById('login-password').value;
            this.login(uname, pword);
        });
    }

    // 4. Agents & MCP Hub Page
    renderAgentsPlayground() {
        const mockModeChecked = this.state.config.mock_agent ? 'checked' : '';
        const modeBadgeClass = this.state.config.mock_agent ? 'offline' : 'online';
        const modeBadgeText = this.state.config.mock_agent ? 'Mock Mode' : 'Live Gemini Mode';

        this.mount.innerHTML = `
            <div class="page-hero">
                <h2>🤖 AI Agents &amp; MCP Hub</h2>
                <p>Interact with task-specific agents and monitor Firestore JSON-RPC telemetry</p>
            </div>

            <div class="card" style="padding:16px 20px;">
                <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:14px;margin-bottom:14px;">
                    <div style="display:flex;align-items:center;gap:10px;">
                        <label class="switch-container" style="display:flex;align-items:center;gap:8px;cursor:pointer;user-select:none;">
                            <input type="checkbox" id="toggle-mock-mode" ${mockModeChecked} onchange="app.toggleMockModeState(this.checked)">
                            <strong>Default Local Mock Mode</strong>
                        </label>
                    </div>
                    <div>
                        <span class="badge ${modeBadgeClass}" id="mode-status-badge"><span class="bdot"></span>${modeBadgeText}</span>
                    </div>
                </div>
                <div style="display:flex;flex-wrap:wrap;gap:12px;border-top:1px solid var(--border);padding-top:14px;align-items:flex-end;">
                    ${this.state.config.is_local ? `
                    <div style="flex:1;min-width:200px;">
                        <label style="font-size:0.78rem;color:var(--text-lt);display:block;margin-bottom:4px;">Gemini API Key <span style="opacity:0.7;">(session only)</span></label>
                        <input type="password" id="agent-api-key"
                            placeholder="${this.state.config.has_key ? '•••••••••••••••• (Configured)' : 'Enter Gemini API key…'}"
                            style="font-size:0.86rem;width:100%;">
                    </div>
                    ` : ''}
                    <div style="min-width:180px;">
                        <label style="font-size:0.78rem;color:var(--text-lt);display:block;margin-bottom:4px;">Gemini Model</label>
                        <select id="agent-gemini-model" style="font-size:0.86rem;" onchange="app.updateGeminiModel(this.value)">
                            <option value="models/gemini-2.5-flash" ${this.state.config.selected_model === 'models/gemini-2.5-flash' ? 'selected' : ''}>gemini-2.5-flash</option>
                            <option value="models/gemini-2.5-flash-lite" ${this.state.config.selected_model === 'models/gemini-2.5-flash-lite' ? 'selected' : ''}>gemini-2.5-flash-lite</option>
                            <option value="models/gemini-2.5-pro" ${this.state.config.selected_model === 'models/gemini-2.5-pro' ? 'selected' : ''}>gemini-2.5-pro</option>
                        </select>
                    </div>
                    ${this.state.config.is_local ? `
                    <button class="btn btn-secondary" style="min-height:36px;" onclick="app.updateApiKey()">Save Key</button>
                    ` : ''}
                </div>
            </div>

            <div class="ornament">❋  ✦  ❋</div>

            <!-- Tab Layout -->
            <div class="tabs-header">
                <button class="tab-btn active" onclick="app.switchDashboardTab('play')">🎮 Playground</button>
                <button class="tab-btn" onclick="app.switchDashboardTab('skills')">📜 Skills</button>
                <button class="tab-btn" onclick="app.switchDashboardTab('mcp')">🔌 MCP Tools</button>
                <button class="tab-btn" onclick="app.switchDashboardTab('con')">🖥 RPC Console</button>
            </div>

            <!-- Playground Tab -->
            <div id="tab-play" class="tab-content active">
                <div class="home-grid">
                    <div class="home-left">
                        <h4 style="margin-bottom:12px;">1. Select AI Agent</h4>
                        <div class="agent-select-grid">
                            <div class="agent-card selected" data-agent="Event Architect Agent" onclick="app.selectAgent(this)">
                                <div class="agent-card-title">📅 Event Architect Agent</div>
                                <div class="agent-card-desc">Schedules events and provisions registration forms.<br><strong>Skill:</strong> EventPlannerSkill.md</div>
                            </div>
                            <div class="agent-card" data-agent="Cultural Blogger Agent" onclick="app.selectAgent(this)">
                                <div class="agent-card-title">✍️ Cultural Blogger Agent</div>
                                <div class="agent-card-desc">Drafts community stories and blog posts.<br><strong>Skill:</strong> MarathiCultureSkill.md</div>
                            </div>
                            <div class="agent-card" data-agent="DB Connection Agent" onclick="app.selectAgent(this)">
                                <div class="agent-card-title">💾 DB Connection Agent</div>
                                <div class="agent-card-desc">Queries Firestore metrics and handles database cleanups.</div>
                            </div>
                        </div>
                    </div>
                    <div class="home-right">
                        <h4 style="margin-bottom:12px;">2. Submit Prompt</h4>
                        <form id="agentCommandForm">
                            <div class="form-group">
                                <label for="agent-prompt" id="agent-prompt-label">Command for Event Architect Agent</label>
                                <textarea id="agent-prompt" rows="4" required placeholder="e.g. Create an event titled Diwali Gathering on November 2026 with entry fee £15"></textarea>
                            </div>
                            <button type="submit" class="btn btn-primary btn-full" id="btn-run-agent">▶ Execute Agent</button>
                        </form>
                    </div>
                </div>

                <div id="agent-execution-result-mount" style="margin-top:20px;"></div>
            </div>

            <!-- Skills Tab -->
            <div id="tab-skills" class="tab-content">
                <div class="skills-grid">
                    <div class="skill-code-card">
                        <div class="skill-title-bar">skills/EventPlannerSkill.md</div>
                        <pre class="skill-body-text" id="skill-event-text">Loading...</pre>
                    </div>
                    <div class="skill-code-card">
                        <div class="skill-title-bar">skills/MarathiCultureSkill.md</div>
                        <pre class="skill-body-text" id="skill-culture-text">Loading...</pre>
                    </div>
                </div>
            </div>

            <!-- MCP Tools Tab -->
            <div id="tab-mcp" class="tab-content">
                <div id="mcp-tools-list-mount">Loading registered MCP schemas...</div>
            </div>

            <!-- RPC Console Tab -->
            <div id="tab-con" class="tab-content">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <strong>Live JSON-RPC 2.0 Firestore Traffic Console</strong>
                    <button class="btn btn-secondary" style="min-height:30px;padding:4px 14px;width:auto;" onclick="app.clearLogs()">Clear Console</button>
                </div>
                <div class="terminal-console" id="rpcConsoleMount">
                    <div class="terminal-line">Console active. Execute agent commands or interact with the database to stream logs...</div>
                </div>
            </div>
        `;

        this.selectedAgentName = "Event Architect Agent";
        
        // Playground execution listener
        document.getElementById('agentCommandForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.executeAgentCommand();
        });

        // Trigger loading of background info for tabs
        this.loadSkillsAndToolsData();
        this.updateTerminalConsole();
    }

    selectAgent(cardElement) {
        document.querySelectorAll('.agent-card').forEach(c => c.classList.remove('selected'));
        cardElement.classList.add('selected');
        
        const agent = cardElement.getAttribute('data-agent');
        this.selectedAgentName = agent;
        
        const label = document.getElementById('agent-prompt-label');
        const input = document.getElementById('agent-prompt');
        
        label.innerText = `Command for ${agent}`;
        
        const placeholders = {
            "Event Architect Agent": "e.g., Create an event titled Diwali Gathering on November 2026 with entry fee £15",
            "Cultural Blogger Agent": "e.g., Write a blog titled Celebrating Kojagiri with content about the moonlit night rituals",
            "DB Connection Agent": "e.g., Show database stats  OR  Clean and reset the database"
        };
        input.placeholder = placeholders[agent];
        input.value = '';
    }

    async loadSkillsAndToolsData() {
        try {
            // Fetch skill texts
            const eventRes = await fetch('/api/skills/EventPlannerSkill.md');
            const eventText = await eventRes.text();
            document.getElementById('skill-event-text').textContent = eventText;

            const cultureRes = await fetch('/api/skills/MarathiCultureSkill.md');
            const cultureText = await cultureRes.text();
            document.getElementById('skill-culture-text').textContent = cultureText;

            // Fetch MCP tools schema
            const mcpTools = await this.apiFetch('/api/mcp/tools');
            const mount = document.getElementById('mcp-tools-list-mount');
            
            if (mcpTools && mcpTools.length > 0) {
                mount.innerHTML = mcpTools.map(tool => `
                    <div class="card" style="border-top:3.5px solid var(--gold);padding:18px;margin-bottom:12px;">
                        <div style="font-family:monospace;font-weight:700;color:var(--saffron);margin-bottom:6px;">${tool.name}</div>
                        <p style="font-size:0.86rem;margin-bottom:10px;">${tool.description}</p>
                        <details>
                            <summary style="font-size:0.78rem;cursor:pointer;color:var(--text-lt);">Input Schema</summary>
                            <pre style="font-size:0.75rem;background:var(--cream);padding:10px;border-radius:6px;border:1px solid var(--border);margin-top:6px;overflow-x:auto;">${JSON.stringify(tool.inputSchema, null, 2)}</pre>
                        </details>
                    </div>
                `).join('');
            } else {
                mount.innerHTML = `<div class="card">No tools found.</div>`;
            }
        } catch (e) {
            console.error(e);
        }
    }

    // Toggle Mock Mode API callback
    async toggleMockModeState(val) {
        try {
            await this.apiFetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mock_agent: val })
            });
            this.state.config.mock_agent = val;
            
            const badge = document.getElementById('mode-status-badge');
            if (val) {
                badge.className = "badge offline";
                badge.innerHTML = `<span class="bdot"></span>Mock Mode`;
                this.showToast('Agent Mock Mode enabled (calls local Firestore MCP directly).', 'info');
            } else {
                badge.className = "badge online";
                badge.innerHTML = `<span class="bdot"></span>Live Gemini Mode`;
                this.showToast('Live Agent Mode enabled (calls Gemini API).', 'success');
            }
        } catch (e) {
            this.showToast('Failed to toggle Mock Mode: ' + e.message, 'error');
        }
    }

    // Tab switcher
    switchDashboardTab(tabId) {
        document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        
        // Find triggering button
        const clickedBtn = Array.from(document.querySelectorAll('.tab-btn'))
                               .find(btn => btn.textContent.includes(tabId === 'play' ? 'Playground' : 
                                                                    tabId === 'skills' ? 'Skills' : 
                                                                    tabId === 'mcp' ? 'Tools' : 'Console'));
        if (clickedBtn) clickedBtn.classList.add('active');
        
        const content = document.getElementById(`tab-${tabId}`);
        if (content) content.classList.add('active');
    }

    // Stream logs to console
    updateTerminalConsole() {
        const consoleMount = document.getElementById('rpcConsoleMount');
        if (!consoleMount) return;
        
        if (this.state.logs.length === 0) {
            consoleMount.innerHTML = `<div class="terminal-line">Console active. Execute agent commands or interact with the database to stream logs...</div>`;
            return;
        }

        consoleMount.innerHTML = this.state.logs.map(log => {
            const timestamp = new Date().toLocaleTimeString();
            const direction = log.direction === 'CLIENT_REQUEST' ? '→ REQUEST' : '← RESPONSE';
            const logClass = log.direction === 'CLIENT_REQUEST' ? 'request' : 'response';
            
            return `
                <div class="terminal-line ${logClass}">[${timestamp}] ${direction}:</div>
                <pre class="terminal-line" style="margin-left:14px;color:#ECEFF1;">${JSON.stringify(log.payload, null, 2)}</pre>
            `;
        }).join('');
        
        // Scroll to bottom
        consoleMount.scrollTop = consoleMount.scrollHeight;
    }

    clearLogs() {
        this.state.logs = [];
        this.updateTerminalConsole();
        this.showToast('Telemetry console cleared.', 'info');
    }

    // Execute Agent Command
    async executeAgentCommand() {
        const prompt = document.getElementById('agent-prompt').value;
        const resultMount = document.getElementById('agent-execution-result-mount');
        const btn = document.getElementById('btn-run-agent');
        
        if (!prompt.trim()) return;

        btn.disabled = true;
        btn.innerText = '🤖 Processing...';
        resultMount.innerHTML = `
            <div class="card" style="border-top: 3.5px solid var(--gold-lt);">
                <h4 style="margin-bottom:10px;">Agent Execution Output</h4>
                <div class="bdot" style="width:12px;height:12px;display:inline-block;margin-right:8px;background:var(--saffron);"></div>
                <span style="color:var(--text-lt);font-style:italic;">Agent is running reasoning logs and querying the database...</span>
            </div>
        `;

        try {
            // Pick up the api_key entered inline on the agents page (if any) and
            // push it to the server config before executing, so it is used for
            // this request without requiring a separate "Save Key" click.
            const inlineKey = (document.getElementById('agent-api-key')?.value || '').trim();
            const inlineModel = document.getElementById('agent-gemini-model')?.value || this.state.config.selected_model;

            if (inlineKey) {
                await this.apiFetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ api_key: inlineKey, selected_model: inlineModel })
                });
                this.state.config.has_key = true;
                this.state.config.selected_model = inlineModel;
            } else if (inlineModel !== this.state.config.selected_model) {
                await this.apiFetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ selected_model: inlineModel })
                });
                this.state.config.selected_model = inlineModel;
            }

            const result = await this.apiFetch('/api/agent/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    agent: this.selectedAgentName,
                    command: prompt
                })
            });

            let reasoningHtml = '';
            if (this.selectedAgentName !== "DB Connection Agent") {
                reasoningHtml = `
                    <div class="reasoning-box">
                        <h4>💭 Agent Reasoning Logs</h4>
                        <p style="font-family:monospace;white-space:pre-wrap;font-size:0.86rem;color:var(--text-md);">${result.reasoning || ''}</p>
                    </div>
                `;
            }

            let metricsHtml = '';
            if (result.db_metrics) {
                metricsHtml = `
                    <div class="metrics-row" style="margin-top:16px;margin-bottom:0;">
                        <div class="metric-card">
                            <div class="metric-label">Events</div>
                            <div class="metric-val">${result.db_metrics.events}</div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-label">Blog Posts</div>
                            <div class="metric-val">${result.db_metrics.blogs}</div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-label">Registrations</div>
                            <div class="metric-val">${result.db_metrics.registrations}</div>
                        </div>
                    </div>
                `;
            }

            resultMount.innerHTML = `
                <div class="card" style="border-top: 4px solid #2E7D32;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                        <h4 style="color:#2E7D32;">✓ Execution Complete</h4>
                        <span class="badge online">Success</span>
                    </div>
                    <div style="font-size:0.95rem;line-height:1.7;">
                        ${result.message}
                    </div>
                    
                    ${metricsHtml}
                    ${reasoningHtml}
                </div>
            `;
            
            this.showToast('Agent execution successful.', 'success');
            document.getElementById('agent-prompt').value = '';
            
            // Highlight Console tab if logs were returned
            if (result.logs_count > 0) {
                this.showToast(`Piped ${result.logs_count} Firestore JSON-RPC messages to telemetry!`, 'info');
            }

        } catch (e) {
            console.error(e);
            this.showToast('Execution failed: ' + e.message, 'error');
            resultMount.innerHTML = `
                <div class="card" style="border-top: 4px solid #C62828;">
                    <h4 style="color:#C62828;margin-bottom:10px;">Execution Failed</h4>
                    <p style="color:var(--text-md);font-size:0.92rem;">${e.message}</p>
                    <div style="margin-top:14px;font-size:0.84rem;color:var(--text-lt);">
                        💡 <strong>Troubleshooting:</strong> If utilizing Live Gemini Mode, ensure your API Key is configured. Otherwise, toggle <strong>Mock Mode</strong> above to execute locally.
                    </div>
                </div>
            `;
        } finally {
            btn.disabled = false;
            btn.innerText = '▶ Execute Agent';
        }
    }

    // 5. Builder Workspace (Static design workflow info)
    renderBuilderWorkspace() {
        this.mount.innerHTML = `
            <div class="page-hero">
                <h2>🏗 Builder Agent Workspace</h2>
                <p>Track how the Antigravity AI agent refactored and constructed this portal</p>
            </div>
            
            <div class="metrics-row">
                <div class="metric-card">
                    <div class="metric-label">Backend Modules</div>
                    <div class="metric-val">FastAPI + Uvicorn</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Frontend Structure</div>
                    <div class="metric-val">Vanilla SPA</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">MCP Channels</div>
                    <div class="metric-val">1 (Firestore API)</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Build Status</div>
                    <div class="metric-val" style="color:#2E7D32;">PASSING</div>
                </div>
            </div>

            <div class="card">
                <div class="sec-head">Construction Timeline</div>
                
                <div class="timeline">
                    <div class="t-node">
                        <div class="t-time">Phase 1 — Audit & Research</div>
                        <div class="t-title">Diagnosing UI Fragmentation</div>
                        <div class="t-desc">Analyzed previous layout. Found page crashes were caused by fragile CSS overrides ('first-of-type' selectors) targeting Streamlit's container widgets, causing overlap.</div>
                    </div>
                    <div class="t-node">
                        <div class="t-time">Phase 2 — Architectural Shift</div>
                        <div class="t-title">Rebuilding as FastAPI Web App</div>
                        <div class="t-desc">Transitioned backend from Streamlit to standard FastAPI. Designed pure HTML5, CSS3, and JS architecture to isolate rendering contexts and provide a robust layout.</div>
                    </div>
                    <div class="t-node">
                        <div class="t-time">Phase 3 — Interactive UI</div>
                        <div class="t-title">Traditional Theme & Multi-Step Wizard</div>
                        <div class="t-desc">Implemented warm traditional Indian colors. Built a responsive top navigation bar, glassmorphism UI cards, and a multi-step registration form modal.</div>
                    </div>
                    <div class="t-node">
                        <div class="t-time">Phase 4 — Agent Playground</div>
                        <div class="t-title">RPC Stream & Skills Viewer</div>
                        <div class="t-desc">Designed an interactive workspace console to display agent reasoning and capture real-time JSON-RPC 2.0 network traffic from the Firestore MCP server.</div>
                    </div>
                    <div class="t-node">
                        <div class="t-time">Phase 5 — Build Verification</div>
                        <div class="t-title">Dockerization & Verification</div>
                        <div class="t-desc">Configured Python Docker image to launch with Uvicorn. Conducted automated and manual UI spot verification for responsive mobile layout. Ready for Cloud Run.</div>
                    </div>
                </div>
            </div>
        `;
    }

    // 6. System Configurations & Database Admin
    renderSystemAdmin() {
        const eventsList = this.state.events || [];
        const blogsList = this.state.blogs || [];
        const regsList = this.state.registrations || [];

        // Registrations Table Rows
        let regsRows = '';
        if (regsList.length === 0) {
            regsRows = `<tr><td colspan="7" style="text-align:center;color:var(--text-lt);font-style:italic;">No registrations received.</td></tr>`;
        } else {
            regsRows = regsList.map(r => {
                const badgeClass = r.status === 'Paid' ? 'online' : 'offline';
                return `
                    <tr>
                        <td><strong>${r.id}</strong></td>
                        <td>${r.name || ''}</td>
                        <td>${r.event || ''}</td>
                        <td>Adults: ${r.adults || 0}<br>Kids: ${r.children || 0}</td>
                        <td><strong>£${(r.total || 0).toFixed(2)}</strong></td>
                        <td><span class="badge ${badgeClass}">${r.status}</span></td>
                        <td>
                            ${r.status !== 'Paid' ? `
                                <button class="btn btn-primary table-action-btn" onclick="app.markRegistrationAsPaid(${r.id})">Mark Paid</button>
                            ` : 'Paid ✓'}
                        </td>
                    </tr>
                `;
            }).join('');
        }

        const isGcpActiveBadge = '';

        this.mount.innerHTML = `
            <div class="page-hero">
                <h2>⚙️ System Configuration &amp; Database Admin</h2>
                <p>Manage event details, publish stories, view registration reports, and modify server properties</p>
            </div>

            <div class="config-row">
                <div class="config-card" style="display:flex;flex-direction:column;justify-content:space-between;">
                    <div>
                        <h4>Database Provider</h4>
                        <p style="font-size:0.75rem;color:var(--text-lt);margin-top:4px;margin-bottom:14px;">Displays active server channel for data persistence</p>
                        <div style="margin-bottom:12px;">${isGcpActiveBadge}</div>
                    </div>
                    <button class="btn btn-secondary" style="min-height:36px;border-color:#C62828;color:#C62828;" onclick="app.resetDatabase()">Reset Database</button>
                </div>
            </div>

            <div class="tabs-header">
                <button class="tab-btn active" onclick="app.switchAdminTab('ev')">🗓 Event Planner</button>
                <button class="tab-btn" onclick="app.switchAdminTab('bl')">📝 Story Publisher</button>
                <button class="tab-btn" onclick="app.switchAdminTab('rg')">🎟 Registrations (${regsList.length})</button>
            </div>

            <!-- Event Planner Tab -->
            <div id="tab-admin-ev" class="tab-content active">
                <div class="card" style="max-width:600px;margin: 0 auto;">
                    <h4 style="margin-bottom:14px;">Schedule a New Event</h4>
                    <form id="adminAddEventForm">
                        <div class="form-group">
                            <label for="event-title-input">Event Title <span class="required">*</span></label>
                            <input type="text" id="event-title-input" required placeholder="e.g. Diwali Festivities 2026">
                        </div>
                        <div class="form-group">
                            <label for="event-date-input">Date <span class="required">*</span></label>
                            <input type="text" id="event-date-input" required placeholder="e.g. November 2026">
                        </div>
                        <div class="form-group">
                            <label for="event-desc-input">Description</label>
                            <textarea id="event-desc-input" rows="4" placeholder="Brief outline of the event timings and agenda"></textarea>
                        </div>
                        <div class="form-group">
                            <label for="event-fee-input">Ticket Fee (£)</label>
                            <input type="number" id="event-fee-input" min="0" step="0.01" value="25.00" placeholder="e.g. 25.00 (set to 0 for free events)">
                        </div>
                        <button type="submit" class="btn btn-primary btn-full">Add Event</button>
                    </form>
                </div>
            </div>

            <!-- Story Publisher Tab -->
            <div id="tab-admin-bl" class="tab-content">
                <div class="card" style="max-width:700px;margin:0 auto;">
                    <h4 style="margin-bottom:14px;">Publish a Cultural Story</h4>
                    <form id="adminAddBlogForm">
                        <div class="form-group">
                            <label for="blog-title-input">Story Title <span class="required">*</span></label>
                            <input type="text" id="blog-title-input" required placeholder="e.g. Ganeshotsav Celebrations 1973">
                        </div>
                        <div class="form-row">
                            <div class="form-group">
                                <label for="blog-author-input">Author <span class="required">*</span></label>
                                <input type="text" id="blog-author-input" required placeholder="e.g. Archival Committee">
                            </div>
                            <div class="form-group">
                                <label for="blog-date-input">Date</label>
                                <input type="text" id="blog-date-input" placeholder="e.g. July 2026">
                            </div>
                        </div>
                        <div class="form-group">
                            <label for="blog-content-input">Content <span class="required">*</span></label>
                            <textarea id="blog-content-input" rows="8" required placeholder="Full story narrative..."></textarea>
                        </div>
                        <button type="submit" class="btn btn-primary btn-full">Publish Story</button>
                    </form>
                </div>
            </div>

            <!-- Registrations Tab -->
            <div id="tab-admin-rg" class="tab-content">
                <div class="card">
                    <h4 style="margin-bottom:10px;">Event Registrations Report</h4>
                    <div class="table-container">
                        <table class="data-table">
                            <thead>
                                <tr>
                                    <th>Reg ID</th>
                                    <th>Name</th>
                                    <th>Event</th>
                                    <th>Attendees</th>
                                    <th>Amount</th>
                                    <th>Status</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${regsRows}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        `;

        // Bind form listeners
        document.getElementById('adminAddEventForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleAddEvent();
        });

        document.getElementById('adminAddBlogForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleAddBlog();
        });
    }

    switchAdminTab(tabId) {
        // Deactivate all
        document.querySelectorAll('#tab-admin-ev, #tab-admin-bl, #tab-admin-rg').forEach(c => c.classList.remove('active'));
        const tabHeader = document.querySelector('#tab-admin-ev').parentNode.querySelector('.tabs-header');
        tabHeader.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));

        // Find button
        const btnText = tabId === 'ev' ? 'Event Planner' : tabId === 'bl' ? 'Story Publisher' : 'Registrations';
        const clickedBtn = Array.from(tabHeader.querySelectorAll('.tab-btn')).find(btn => btn.textContent.includes(btnText));
        if (clickedBtn) clickedBtn.classList.add('active');

        const content = document.getElementById(`tab-admin-${tabId}`);
        if (content) content.classList.add('active');
    }

    // Update API Key Session override
    async updateApiKey() {
        // Support both the agents-page input (agent-api-key) and the legacy admin input (cfg-api-key)
        const key = (document.getElementById('agent-api-key') ?? document.getElementById('cfg-api-key'))?.value || '';
        try {
            await this.apiFetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ api_key: key })
            });
            this.showToast('Gemini API key updated.', 'success');
            const agentInput = document.getElementById('agent-api-key');
            const cfgInput = document.getElementById('cfg-api-key');
            if (agentInput) agentInput.value = '';
            if (cfgInput) cfgInput.value = '';
            await this.fetchConfig();
            // Re-render whichever page is active to refresh the placeholder
            if (document.getElementById('agent-api-key')) this.renderAgentsPlayground();
            else this.renderSystemAdmin();
        } catch (e) {
            this.showToast('Failed to update API key: ' + e.message, 'error');
        }
    }

    // Update Stripe Key Session override
    async updateStripeKey() {
        const key = document.getElementById('cfg-stripe-key').value;
        try {
            await this.apiFetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ stripe_secret_key: key })
            });
            this.showToast('Stripe API key session override updated.', 'success');
            document.getElementById('cfg-stripe-key').value = '';
            await this.fetchConfig();
            this.renderSystemAdmin();
        } catch (e) {
            this.showToast('Failed to update Stripe key: ' + e.message, 'error');
        }
    }

    // Update Model selection
    async updateGeminiModel(modelName) {
        try {
            await this.apiFetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ selected_model: modelName })
            });
            this.showToast('Gemini model updated to: ' + modelName.split('/').pop(), 'success');
            this.state.config.selected_model = modelName;
        } catch (e) {
            this.showToast('Failed to update model: ' + e.message, 'error');
        }
    }

    // Reset Database
    async resetDatabase() {
        if (!confirm('Are you sure you want to clean and reset the database? This deletes non-Ganeshotsav events.')) return;
        
        try {
            await this.apiFetch('/api/admin/reset', { method: 'POST' });
            this.showToast('Database successfully reset to defaults.', 'success');
            // Reload admin view
            await this.navigate('admin');
        } catch (e) {
            this.showToast('Database reset failed: ' + e.message, 'error');
        }
    }

    // Add new event
    async handleAddEvent() {
        const title = document.getElementById('event-title-input').value;
        const date = document.getElementById('event-date-input').value;
        const desc = document.getElementById('event-desc-input').value;
        const ticketFeeVal = document.getElementById('event-fee-input').value;
        const ticketFee = ticketFeeVal !== '' ? parseFloat(ticketFeeVal) : 25.0;

        try {
            await this.apiFetch('/api/events', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title, date, description: desc, ticket_fee: ticketFee })
            });
            this.showToast(`Event "${title}" scheduled successfully!`, 'success');
            await this.navigate('admin');
        } catch (e) {
            this.showToast('Failed to schedule event: ' + e.message, 'error');
        }
    }

    // Add new blog
    async handleAddBlog() {
        const title = document.getElementById('blog-title-input').value;
        const author = document.getElementById('blog-author-input').value;
        const date = document.getElementById('blog-date-input').value;
        const content = document.getElementById('blog-content-input').value;

        try {
            await this.apiFetch('/api/blogs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title, author, date, content })
            });
            this.showToast(`Story "${title}" published successfully!`, 'success');
            await this.navigate('admin');
        } catch (e) {
            this.showToast('Failed to publish story: ' + e.message, 'error');
        }
    }

    // Mark registration as paid
    async markRegistrationAsPaid(regId) {
        try {
            await this.apiFetch(`/api/registrations/${regId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: 'Paid' })
            });
            this.showToast(`Registration #${regId} status marked Paid!`, 'success');
            await this.navigate('admin');
            this.switchAdminTab('rg');
        } catch (e) {
            this.showToast('Failed to update status: ' + e.message, 'error');
        }
    }

    // ─── Registration Wizard Modal Functions ─────────────────────────────────
    openRegistrationModal(eventTitle, fee) {
        this.state.regEvent = { title: eventTitle, fee };
        this.state.regStep = 1;
        this.state.regData = {};
        
        // Reset forms
        document.getElementById('regFormStep1').reset();
        document.getElementById('regFormStep2').reset();
        
        document.getElementById('regModalTitle').innerText = `📋 Register: ${eventTitle}`;
        document.getElementById('regModalTotalFee').innerText = `£${fee.toFixed(2)}`;
        
        // Setup default counts
        document.getElementById('reg-adults').value = 1;
        document.getElementById('reg-children').value = 0;
        
        // Trigger inputs rendering
        this.toggleCulturalInputs();
        this.showRegistrationStep(1);

        document.getElementById('regModal').classList.add('open');
        
        // Bind change listener to recalculate fee live
        const adultsInput = document.getElementById('reg-adults');
        const childrenInput = document.getElementById('reg-children');
        const recalculate = () => {
            const adults = parseInt(adultsInput.value) || 0;
            const total = adults * fee;
            document.getElementById('regModalTotalFee').innerText = `£${total.toFixed(2)}`;
        };
        adultsInput.oninput = recalculate;
        childrenInput.oninput = recalculate;
    }

    closeRegistrationModal() {
        document.getElementById('regModal').classList.remove('open');
        this.state.regEvent = null;
        // If we registered on home page, trigger page refresh to reload event lists
        if (this.state.page === 'home') {
            this.navigate('home');
        }
    }

    showRegistrationStep(step) {
        this.state.regStep = step;
        
        // Hide all forms
        document.getElementById('regFormStep1').style.display = 'none';
        document.getElementById('regFormStep2').style.display = 'none';
        document.getElementById('regStep3').style.display = 'none';
        
        // Deactivate all step indicators
        document.getElementById('indicator-1').className = 'step-indicator';
        document.getElementById('indicator-2').className = 'step-indicator';
        document.getElementById('indicator-3').className = 'step-indicator';

        if (step === 1) {
            document.getElementById('regFormStep1').style.display = 'block';
            document.getElementById('indicator-1').className = 'step-indicator active';
        } else if (step === 2) {
            document.getElementById('regFormStep2').style.display = 'block';
            document.getElementById('indicator-1').className = 'step-indicator completed';
            document.getElementById('indicator-2').className = 'step-indicator active';
        } else if (step === 3) {
            document.getElementById('regStep3').style.display = 'block';
            document.getElementById('indicator-1').className = 'step-indicator completed';
            document.getElementById('indicator-2').className = 'step-indicator completed';
            document.getElementById('indicator-3').className = 'step-indicator active';
        }
    }

    prevRegistrationStep() {
        if (this.state.regStep > 1) {
            this.showRegistrationStep(this.state.regStep - 1);
        }
    }

    handleRegistrationStep1() {
        const fn = document.getElementById('reg-firstName').value;
        const ln = document.getElementById('reg-lastName').value;
        const email = document.getElementById('reg-email').value;
        const phone = document.getElementById('reg-phone').value;
        const city = document.getElementById('reg-city').value;

        this.state.regData = {
            name: `${fn} ${ln}`,
            email,
            phone,
            residence: city
        };

        this.showRegistrationStep(2);
    }

    async handleRegistrationStep2() {
        const adults = parseInt(document.getElementById('reg-adults').value) || 0;
        const children = parseInt(document.getElementById('reg-children').value) || 0;
        const participate = document.getElementById('reg-participate').value;
        
        let participantNames = '';
        let performanceType = '';
        if (participate === 'Yes') {
            participantNames = document.getElementById('reg-participantNames').value;
            performanceType = document.getElementById('reg-performanceType').value;
        }

        const comments = document.getElementById('reg-comments').value;

        if (adults === 0 && children === 0) {
            this.showToast('Please register at least one attendee.', 'warning');
            return;
        }

        const total = adults * this.state.regEvent.fee;

        const regPayload = {
            event: this.state.regEvent.title,
            ...this.state.regData,
            adults,
            children,
            total,
            cultural_interest: participate,
            participant_names: participantNames,
            performance_type: performanceType,
            comments,
            status: 'Pending Payment',
            timestamp: new Date().toISOString()
        };

        try {
            const btn = document.querySelector('#regFormStep2 button[type="submit"]');
            if (btn) {
                btn.disabled = true;
                btn.innerText = '💳 Initiating Payment...';
            }

            const result = await this.apiFetch('/api/payments/create-checkout-session', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(regPayload)
            });

            this.showToast('Redirecting to Stripe Sandbox...', 'success');
            
            // Redirect to Stripe checkout (mock or real sandbox)
            setTimeout(() => {
                window.location.href = result.checkout_url;
            }, 800);
            
        } catch (e) {
            this.showToast('Checkout failed: ' + e.message, 'error');
            const btn = document.querySelector('#regFormStep2 button[type="submit"]');
            if (btn) {
                btn.disabled = false;
                btn.innerText = 'Proceed to Payment →';
            }
        }
    }

    toggleCulturalInputs() {
        const val = document.getElementById('reg-participate').value;
        const group = document.getElementById('cultural-inputs-group');
        
        if (val === 'Yes') {
            group.style.display = 'block';
            document.getElementById('reg-participantNames').required = true;
            document.getElementById('reg-performanceType').required = true;
        } else {
            group.style.display = 'none';
            document.getElementById('reg-participantNames').required = false;
            document.getElementById('reg-performanceType').required = false;
        }
    }

    async handlePaymentRedirect(status, regId) {
        // Parse additional parameters if success
        const urlParams = new URLSearchParams(window.location.search);
        const eventName = urlParams.get('event') || '';
        const totalFee = parseFloat(urlParams.get('total')) || 0;
        const userName = urlParams.get('name') || '';
        const userEmail = urlParams.get('email') || '';

        // Clear URL query parameters so refresh doesn't trigger again
        window.history.replaceState({}, document.title, window.location.pathname);
        
        // Always navigate to home first so page renders
        this.state.page = 'home';
        this.updateNavUI();
        
        await this.fetchEvents();
        await this.fetchConfig();
        this.renderHome();

        if (status === 'success') {
            this.showToast('💳 Payment verified and completed!', 'success');
            
            // Open the registration modal directly in step 3 success!
            this.state.regEvent = { title: eventName, fee: totalFee };
            this.state.regStep = 3;
            
            // Show modal
            document.getElementById('regModalTitle').innerText = `📋 Registration Successful`;
            
            // Set final step summary values
            document.getElementById('summaryName').innerText = `Thank you, ${userName}!`;
            document.getElementById('summaryEvent').innerText = eventName;
            document.getElementById('summaryFee').innerText = `£${totalFee.toFixed(2)}`;
            document.getElementById('summaryEmail').innerText = userEmail;
            
            // Show badge with status
            const summaryText = document.querySelector('.summary-text');
            if (summaryText) {
                summaryText.innerHTML = `
                    Event: <strong>${eventName}</strong><br>
                    Amount Paid: <strong>£${totalFee.toFixed(2)}</strong><br>
                    Status: <span class="badge online">Paid</span><br>
                    A confirmation and receipt email has been sent to: <strong>${userEmail}</strong>
                `;
            }
            
            this.showRegistrationStep(3);
            document.getElementById('regModal').classList.add('open');
        } else if (status === 'cancelled') {
            this.showToast('⚠️ Payment cancelled by user.', 'warning');
        } else {
            this.showToast('❌ Payment verification failed.', 'error');
        }
    }

    // ─── Toasts / Notifications ──────────────────────────────────────────────
    showToast(message, type = 'info') {
        const container = document.getElementById('toastContainer');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        let icon = 'ℹ️';
        if (type === 'success') icon = '✓';
        if (type === 'error') icon = '❌';
        if (type === 'warning') icon = '⚠️';

        toast.innerHTML = `
            <div style="display:flex;align-items:center;gap:8px;">
                <span>${icon}</span>
                <span>${message}</span>
            </div>
            <button class="toast-close">&times;</button>
        `;

        container.appendChild(toast);

        // Bind close button
        toast.querySelector('.toast-close').onclick = () => {
            toast.remove();
        };

        // Auto remove
        setTimeout(() => {
            if (toast.parentNode) {
                toast.classList.add('fade-out');
                setTimeout(() => toast.remove(), 250);
            }
        }, 4000);
    }
}

// Initialise App
let app;
window.addEventListener('DOMContentLoaded', () => {
    app = new NorwemaApp();
    
    // Check for payment redirect query parameters
    const urlParams = new URLSearchParams(window.location.search);
    const paymentStatus = urlParams.get('payment');
    const regId = urlParams.get('reg_id');
    
    if (paymentStatus && regId) {
        app.handlePaymentRedirect(paymentStatus, regId);
    } else {
        // Default page route
        app.navigate('home');
    }
});
