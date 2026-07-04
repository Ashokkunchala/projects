/**
 * Cloudflare AI Agent for Infrastructure Analysis
 * Provides intelligent infrastructure validation, cost optimization, security analysis,
 * and conversational chat powered by Llama 3.1 8B.
 */

export interface Env {
  AI: any;
  CACHE: KVNamespace;
  RATE_LIMIT: KVNamespace;
  DB: D1Database;
  STORAGE: R2Bucket;
  ANALYSIS_QUEUE: any;
  ENVIRONMENT: string;
  ALLOWED_ORIGINS: string;
}

const AI_MODEL_FAST = '@cf/meta/llama-3.2-3b-instruct';
const AI_MODEL_SMART = '@cf/meta/llama-3.1-8b-instruct-fp8';
const AI_MODEL = AI_MODEL_FAST; // Default to fast for analyze/validate/explain

interface AnalysisRequest {
  action: 'analyze' | 'validate' | 'optimize' | 'explain';
  content: string;
  file_type: 'terraform' | 'cloudformation' | 'kubernetes' | 'docker-compose';
  options?: {
    focus?: 'cost' | 'security' | 'performance' | 'all';
    provider?: 'aws' | 'azure' | 'gcp';
  };
}

interface ChatRequest {
  messages: Array<{ role: 'user' | 'assistant' | 'system'; content: string }>;
  context?: {
    analysis_id?: string;
    analysis_result?: Record<string, unknown>;
    scan_data?: Record<string, unknown>;
    page?: string;
    user_services?: string[];
  };
  conversation_id?: number;
  backend_user_id?: number;
  max_tokens?: number;
  temperature?: number;
  stream?: boolean;
}

interface AnalysisResult {
  success: boolean;
  type: string;
  summary: string;
  resources: ResourceInfo[];
  connections: ConnectionInfo[];
  issues: Issue[];
  suggestions: Suggestion[];
  cost_estimate?: CostEstimate;
  security_score?: number;
  compliance_status?: ComplianceStatus;
}

interface ResourceInfo {
  id: string;
  type: string;
  name: string;
  category: string;
  config: Record<string, unknown>;
  estimated_cost: number;
  free_tier_eligible: boolean;
  security_concerns: string[];
}

interface ConnectionInfo {
  source: string;
  target: string;
  type: string;
  valid: boolean;
  description: string;
}

interface Issue {
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
  category: string;
  resource: string;
  message: string;
  explanation: string;
  fix: string;
  fix_example?: string;
}

interface Suggestion {
  type: 'cost' | 'security' | 'performance' | 'reliability';
  priority: number;
  title: string;
  description: string;
  impact: string;
  implementation: string;
}

interface CostEstimate {
  monthly_total: number;
  breakdown: Record<string, number>;
  optimization_potential: number;
  recommendations: string[];
}

interface ComplianceStatus {
  score: number;
  violations: string[];
  recommendations: string[];
}

// ─── Main Handler ─────────────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    const corsHeaders: Record<string, string> = {
      'Access-Control-Allow-Origin': env.ALLOWED_ORIGINS || '*',
      'Access-Control-Allow-Methods': 'GET, POST, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Backend-User-Id',
    };

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    try {
      // Existing endpoints
      if (url.pathname === '/api/agent/analyze' && request.method === 'POST') {
        return this.handleAnalyze(request, env, corsHeaders);
      }
      if (url.pathname === '/api/agent/validate' && request.method === 'POST') {
        return this.handleValidate(request, env, corsHeaders);
      }
      if (url.pathname === '/api/agent/explain' && request.method === 'POST') {
        return this.handleExplain(request, env, corsHeaders);
      }
      if (url.pathname === '/api/agent/health') {
        return this.handleHealth(env, corsHeaders);
      }
      if (url.pathname === '/api/agent/complete' && request.method === 'POST') {
        return this.handleComplete(request, env, corsHeaders);
      }

      // New chat endpoints
      if (url.pathname === '/api/agent/chat' && request.method === 'POST') {
        return this.handleChat(request, env, corsHeaders, ctx);
      }

      // Conversation CRUD
      if (url.pathname === '/api/agent/conversations' && request.method === 'GET') {
        return this.handleListConversations(request, env, corsHeaders);
      }
      if (url.pathname === '/api/agent/conversations' && request.method === 'POST') {
        return this.handleCreateConversation(request, env, corsHeaders);
      }
      if (url.pathname.match(/^\/api\/agent\/conversations\/\d+$/) && request.method === 'GET') {
        const id = parseInt(url.pathname.split('/').pop() || '0');
        return this.handleGetConversationMessages(id, env, corsHeaders);
      }
      if (url.pathname.match(/^\/api\/agent\/conversations\/\d+$/) && request.method === 'DELETE') {
        const id = parseInt(url.pathname.split('/').pop() || '0');
        return this.handleDeleteConversation(id, env, corsHeaders);
      }

      return new Response('Not Found', { status: 404, headers: corsHeaders });
    } catch (error) {
      console.error('Agent error:', error);
      return new Response(
        JSON.stringify({ error: 'Internal server error' }),
        { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }
  },

  // ─── Chat Handler (SSE Streaming) ──────────────────────────────────────────

  async handleChat(request: Request, env: Env, corsHeaders: Record<string, string>, ctx: ExecutionContext): Promise<Response> {
    let req: ChatRequest;
    try {
      req = await request.json();
      if (!req.messages || !Array.isArray(req.messages) || req.messages.length === 0) {
        return jsonResponse(corsHeaders, { error: 'messages array is required' }, 400);
      }
    } catch {
      return jsonResponse(corsHeaders, { error: 'Invalid JSON body' }, 400);
    }

    const backendUserId = request.headers.get('X-Backend-User-Id') || req.backend_user_id?.toString() || 'anonymous';

    // Rate limit chat: 30 req/min per user
    const rlKey = `chat:${backendUserId}:${Math.floor(Date.now() / 60000)}`;
    let chatCount = 0;
    try {
      const raw = await env.RATE_LIMIT.get(rlKey);
      chatCount = raw ? parseInt(raw, 10) : 0;
    } catch { /* allow */ }
    if (chatCount >= 30) {
      return jsonResponse(corsHeaders, { error: 'Chat rate limit exceeded (30/min)' }, 429);
    }
    await env.RATE_LIMIT.put(rlKey, String(chatCount + 1), { expirationTtl: 120 });

    // Build system prompt with context
    const systemPrompt = this.buildChatSystemPrompt(req.context);
    const messages = [
      { role: 'system' as const, content: systemPrompt },
      ...req.messages.slice(-20), // Keep last 20 messages for context window
    ];

    const maxTokens = req.max_tokens || 2048;
    const temperature = req.temperature ?? 0.3;

    // Streaming mode
    if (req.stream) {
      return this.streamChatResponse(messages, maxTokens, temperature, env, corsHeaders, ctx, req, backendUserId);
    }

    // Non-streaming mode
    const aiBinding = env.AI || (env as any).ai;
    let aiResponse;
    try {
      aiResponse = await (aiBinding as any).run?.(AI_MODEL_SMART, {
        messages,
        max_tokens: maxTokens,
        temperature,
      });
    } catch (e) {
      console.error('Chat AI call failed:', e);
      return jsonResponse(corsHeaders, { error: 'AI service unavailable' }, 502);
    }

    if (!aiResponse) {
      return jsonResponse(corsHeaders, { error: 'AI returned empty response' }, 502);
    }

    const responseText = aiResponse.response || '';

    // Save to D1 in background
    ctx.waitUntil(this.saveChatMessages(env, backendUserId, req, responseText));

    return jsonResponse(corsHeaders, { response: responseText });
  },

  // ─── Streaming Chat Response ───────────────────────────────────────────────

  async streamChatResponse(
    messages: Array<{ role: string; content: string }>,
    maxTokens: number,
    temperature: number,
    env: Env,
    corsHeaders: Record<string, string>,
    ctx: ExecutionContext,
    req: ChatRequest,
    backendUserId: string,
  ): Promise<Response> {
    const aiBinding = env.AI || (env as any).ai;

    const { readable, writable } = new TransformStream();
    const writer = writable.getWriter();
    const encoder = new TextEncoder();

    ctx.waitUntil((async () => {
      let fullResponse = '';
      try {
        const stream = await (aiBinding as any).run?.(AI_MODEL_SMART, {
          messages,
          max_tokens: maxTokens,
          temperature,
          stream: true,
        });

        if (stream) {
          for await (const chunk of stream) {
            const token = chunk.response || '';
            fullResponse += token;
            await writer.write(encoder.encode(`data: ${JSON.stringify({ token })}\n\n`));
          }
        } else {
          // Fallback: non-streaming response sent as single chunk
          const fallback = await (aiBinding as any).run?.(AI_MODEL_SMART, {
            messages,
            max_tokens: maxTokens,
            temperature,
          });
          fullResponse = fallback?.response || 'No response';
          await writer.write(encoder.encode(`data: ${JSON.stringify({ token: fullResponse })}\n\n`));
        }
      } catch (e) {
        console.error('Streaming AI call failed:', e);
        await writer.write(encoder.encode(`data: ${JSON.stringify({ error: 'AI service unavailable' })}\n\n`));
      }

      await writer.write(encoder.encode('data: [DONE]\n\n'));
      await writer.close();

      // Save messages to D1
      if (fullResponse) {
        await this.saveChatMessages(env, backendUserId, req, fullResponse);
      }
    })());

    return new Response(readable, {
      headers: {
        ...corsHeaders,
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
      },
    });
  },

  // ─── Save Chat Messages to D1 ──────────────────────────────────────────────

  async saveChatMessages(env: Env, backendUserId: string, req: ChatRequest, assistantResponse: string): Promise<void> {
    try {
      let conversationId = req.conversation_id;

      // Auto-create conversation if none provided
      if (!conversationId) {
        const firstUserMsg = req.messages.find(m => m.role === 'user')?.content || 'New conversation';
        const title = firstUserMsg.slice(0, 80) + (firstUserMsg.length > 80 ? '...' : '');
        const result = await env.DB.prepare(
          'INSERT INTO conversations (backend_user_id, title) VALUES (?, ?)'
        ).bind(parseInt(backendUserId) || 0, title).run();
        conversationId = result.meta?.last_row_id as number;
      }

      if (!conversationId) return;

      // Save the last user message
      const lastUserMsg = req.messages[req.messages.length - 1];
      if (lastUserMsg && lastUserMsg.role === 'user') {
        const page = req.context?.page || null;
        const analysisId = req.context?.analysis_id || null;
        await env.DB.prepare(
          'INSERT INTO messages (conversation_id, role, content, metadata) VALUES (?, ?, ?, ?)'
        ).bind(conversationId, 'user', lastUserMsg.content, JSON.stringify({ page, analysis_id: analysisId })).run();
      }

      // Save assistant response
      await env.DB.prepare(
        'INSERT INTO messages (conversation_id, role, content, model_used) VALUES (?, ?, ?, ?)'
      ).bind(conversationId, 'assistant', assistantResponse, 'llama-3.1-8b').run();

      // Update conversation timestamp
      await env.DB.prepare(
        'UPDATE conversations SET updated_at = datetime("now") WHERE id = ?'
      ).bind(conversationId).run();
    } catch (e) {
      console.error('Failed to save chat messages:', e);
    }
  },

  // ─── Conversation CRUD ─────────────────────────────────────────────────────

  async handleListConversations(request: Request, env: Env, corsHeaders: Record<string, string>): Promise<Response> {
    const url = new URL(request.url);
    const backendUserId = url.searchParams.get('user_id') || '0';
    try {
      const { results } = await env.DB.prepare(
        'SELECT id, title, created_at, updated_at FROM conversations WHERE backend_user_id = ? ORDER BY updated_at DESC LIMIT 50'
      ).bind(parseInt(backendUserId)).all();
      return jsonResponse(corsHeaders, { conversations: results });
    } catch (e) {
      return jsonResponse(corsHeaders, { conversations: [] });
    }
  },

  async handleCreateConversation(request: Request, env: Env, corsHeaders: Record<string, string>): Promise<Response> {
    const body = await request.json().catch(() => ({}));
    const backendUserId = request.headers.get('X-Backend-User-Id') || '0';
    const title = body.title || 'New conversation';
    try {
      const result = await env.DB.prepare(
        'INSERT INTO conversations (backend_user_id, title) VALUES (?, ?)'
      ).bind(parseInt(backendUserId), title).run();
      return jsonResponse(corsHeaders, { id: result.meta?.last_row_id, title, created_at: new Date().toISOString() }, 201);
    } catch (e) {
      return jsonResponse(corsHeaders, { error: 'Failed to create conversation' }, 500);
    }
  },

  async handleGetConversationMessages(conversationId: number, env: Env, corsHeaders: Record<string, string>): Promise<Response> {
    try {
      const { results } = await env.DB.prepare(
        'SELECT id, role, content, model_used, metadata, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at ASC'
      ).bind(conversationId).all();
      return jsonResponse(corsHeaders, { messages: results });
    } catch (e) {
      return jsonResponse(corsHeaders, { messages: [] });
    }
  },

  async handleDeleteConversation(conversationId: number, env: Env, corsHeaders: Record<string, string>): Promise<Response> {
    try {
      await env.DB.prepare('DELETE FROM messages WHERE conversation_id = ?').bind(conversationId).run();
      await env.DB.prepare('DELETE FROM conversations WHERE id = ?').bind(conversationId).run();
      return jsonResponse(corsHeaders, { success: true });
    } catch (e) {
      return jsonResponse(corsHeaders, { error: 'Failed to delete conversation' }, 500);
    }
  },

  // ─── Chat System Prompt Builder ────────────────────────────────────────────

  buildChatSystemPrompt(context?: ChatRequest['context']): string {
    let system = `You are the AI Cost Detective — an expert cloud infrastructure architect and cost optimization advisor. You help users understand their cloud infrastructure, identify waste, optimize costs, and improve security.

Key capabilities:
- Analyze cloud resources across AWS, Azure, and GCP
- Explain cost anomalies and provide savings recommendations
- Generate fix commands for infrastructure issues
- Help with Terraform/CloudFormation code
- Check compliance with security benchmarks

Response guidelines:
- Be concise and actionable. Focus on the most impactful advice first.
- Use specific numbers when discussing costs ($X/month savings).
- When suggesting fixes, provide the exact CLI command.
- Use markdown formatting: **bold** for emphasis, \`code\` for commands, and bullet points for lists.
- If you don't have enough context, ask clarifying questions.`;

    if (context?.page) {
      const pageContext: Record<string, string> = {
        '/': 'The user is on the Dashboard. Provide an overview of their cloud health and top priorities.',
        '/report': 'The user is viewing a scan report. Help them understand the findings and prioritize fixes.',
        '/analyze': 'The user is configuring or running a scan. Help them select the right services and regions.',
        '/history': 'The user is reviewing scan history. Help them compare results over time.',
        '/estimate': 'The user is estimating infrastructure costs. Help them understand cost breakdowns.',
        '/infra-visualizer': 'The user is viewing infrastructure diagrams. Help them understand resource connections.',
        '/free-tier': 'The user is checking free tier usage. Help them optimize within free tier limits.',
        '/ai-agent': 'The user is on the AI Agent page. Help them analyze infrastructure code.',
      };
      const ctx = pageContext[context.page];
      if (ctx) system += `\n\nCurrent context: ${ctx}`;
    }

    if (context?.analysis_result) {
      const result = context.analysis_result;
      const issues = (result.issues as Issue[]) || [];
      const highIssues = issues.filter(i => i.severity === 'high' || i.severity === 'critical');
      const totalSavings = result.estimated_monthly_savings || 0;

      system += `\n\nCurrent scan analysis context:
- Resources scanned: ${result.total_resources || 0}
- Issues found: ${result.issues_found || 0}
- High/critical issues: ${highIssues.length}
- Estimated monthly savings: $${totalSavings}/month
- Top issues: ${highIssues.slice(0, 5).map((i: Issue) => `${i.severity}: ${i.message}`).join('; ')}`;
    }

    if (context?.user_services && context.user_services.length > 0) {
      system += `\n\nUser's active AWS services: ${context.user_services.join(', ')}`;
    }

    return system;
  },

  // ─── Analyze Handler (upgraded to 8B) ─────────────────────────────────────

  async handleAnalyze(request: Request, env: Env, corsHeaders: Record<string, string>): Promise<Response> {
    let req: AnalysisRequest;
    try {
      req = await request.json();
      if (!req.content || typeof req.content !== 'string' || req.content.length > 50000) {
        return jsonResponse(corsHeaders, { error: 'Invalid request: content must be a string (max 50KB)' }, 400);
      }
      if (req.file_type && !['terraform', 'cloudformation', 'kubernetes', 'docker-compose'].includes(req.file_type)) {
        return jsonResponse(corsHeaders, { error: `Unsupported file_type: ${req.file_type}` }, 400);
      }
    } catch {
      return jsonResponse(corsHeaders, { error: 'Invalid JSON body' }, 400);
    }

    // Rate limiting
    const clientIP = request.headers.get('CF-Connecting-IP') || 'unknown';
    const rateLimitKey = `rate:${clientIP}:${Math.floor(Date.now() / 60000)}`;
    let count = 0;
    try {
      const raw = await env.RATE_LIMIT.get(rateLimitKey);
      count = raw ? parseInt(raw, 10) : 0;
    } catch { /* allow */ }
    if (count >= 10) {
      return jsonResponse(corsHeaders, { error: 'Rate limit exceeded (10 req/min)' }, 429);
    }
    await env.RATE_LIMIT.put(rateLimitKey, String(count + 1), { expirationTtl: 120 });

    let prompt = this.buildAnalysisPrompt(req);
    // Truncate prompt if too long to avoid timeout
    if (prompt.length > 8000) {
      prompt = prompt.slice(0, 8000) + '\n\n[Code truncated for analysis]';
    }
    const aiBinding = env.AI || (env as any).ai;
    let aiResponse;
    try {
      aiResponse = await (aiBinding as any).run?.(AI_MODEL, {
        messages: [
          {
            role: 'system',
            content: `You are an expert cloud infrastructure architect and cost optimizer.
Analyze the provided infrastructure code and return a structured JSON response with:
1. Resource list with types, names, and categories
2. Connections between resources (what references what)
3. Issues found (security, cost, performance)
4. Suggestions for improvement
5. Cost estimates where possible
6. Security and compliance assessment

Always respond with valid JSON. Be specific about issues and provide actionable fixes.`
          },
          { role: 'user', content: prompt }
        ],
        max_tokens: 2048,
        temperature: 0.3,
      });
    } catch (e) {
      console.error('AI call failed:', e);
      aiResponse = null;
    }

    if (!aiResponse) {
      return jsonResponse(corsHeaders, {
        success: true, type: 'analysis',
        summary: `AI analysis unavailable. Analyzed ${req.file_type} code.`,
        resources: [], connections: [],
        issues: [{ severity: 'info', category: 'ai', resource: 'all', message: 'AI service unavailable.', explanation: 'Workers AI binding not configured.', fix: 'Set up AI binding in wrangler.toml.' }],
        suggestions: [],
      });
    }

    const analysisResult = this.parseAIResponse(aiResponse, req);

    // Cache and store
    const contentHash = await this.hashContent(req.content);
    await env.CACHE.put(`analysis:${contentHash}`, JSON.stringify(analysisResult), { expirationTtl: 3600 });
    try {
      await env.DB.prepare(
        'INSERT INTO analyses (content_hash, file_type, result, created_at) VALUES (?, ?, ?, datetime("now"))'
      ).bind(contentHash, req.file_type, JSON.stringify(analysisResult)).run();
    } catch (e) {
      console.error('D1 insert failed', e);
    }

    return jsonResponse(corsHeaders, analysisResult);
  },

  // ─── Validate Handler (upgraded to 8B) ────────────────────────────────────

  async handleValidate(request: Request, env: Env, corsHeaders: Record<string, string>): Promise<Response> {
    let req: AnalysisRequest;
    try {
      req = await request.json();
      if (!req.content || typeof req.content !== 'string' || req.content.length > 50000) {
        return jsonResponse(corsHeaders, { error: 'Invalid request: content must be a string (max 50KB)' }, 400);
      }
    } catch {
      return jsonResponse(corsHeaders, { error: 'Invalid JSON body' }, 400);
    }
    req.options = { ...req.options, focus: 'security' };

    let prompt = this.buildValidationPrompt(req);
    if (prompt.length > 8000) prompt = prompt.slice(0, 8000) + '\n\n[Code truncated]';
    const aiBinding = env.AI || (env as any).ai;
    let aiResponse;
    try {
      aiResponse = await (aiBinding as any).run?.(AI_MODEL, {
        messages: [
          {
            role: 'system',
            content: `You are a cloud security expert. Validate the infrastructure code for:
1. Security vulnerabilities (open ports, public access, missing encryption)
2. Compliance violations (CIS benchmarks, AWS Well-Architected)
3. Best practices violations
4. Missing security controls

Return a structured JSON with severity levels and specific fixes.`
          },
          { role: 'user', content: prompt }
        ],
        max_tokens: 2048,
        temperature: 0.2,
      });
    } catch (e) {
      console.error('AI validation failed:', e);
      aiResponse = null;
    }

    if (!aiResponse) {
      return jsonResponse(corsHeaders, {
        success: true, type: 'validation', summary: 'Validation unavailable.',
        resources: [], connections: [], issues: [], suggestions: [],
      });
    }

    return jsonResponse(corsHeaders, this.parseValidationResponse(aiResponse, req));
  },

  // ─── Explain Handler (upgraded to 8B) ─────────────────────────────────────

  async handleExplain(request: Request, env: Env, corsHeaders: Record<string, string>): Promise<Response> {
    const req: AnalysisRequest = await request.json();
    let code = req.content || '';
    if (code.length > 6000) code = code.slice(0, 6000) + '\n\n[Code truncated]';
    const prompt = `Explain this infrastructure code in simple terms. What does it do? How do the resources connect? What are the costs?

Code:
${code}

Provide:
1. Plain English explanation of what this infrastructure does
2. How resources are connected (data flow)
3. Cost breakdown and optimization opportunities
4. Security posture assessment
5. Recommendations for improvement`;

    const aiBinding = env.AI || (env as any).ai;
    let aiResponse;
    try {
      aiResponse = await (aiBinding as any).run?.(AI_MODEL, {
        messages: [
          { role: 'system', content: 'You are a helpful cloud architect who explains infrastructure in simple, clear language.' },
          { role: 'user', content: prompt }
        ],
        max_tokens: 2048,
        temperature: 0.5,
      });
    } catch (e) {
      console.error('AI explain failed:', e);
      aiResponse = null;
    }

    if (!aiResponse) {
      return jsonResponse(corsHeaders, { success: true, explanation: 'AI explanation service unavailable.', language: 'en' });
    }

    return jsonResponse(corsHeaders, { success: true, explanation: aiResponse.response, language: 'en' });
  },

  // ─── Health Handler (upgraded to 8B) ──────────────────────────────────────

  async handleHealth(env: Env, corsHeaders: Record<string, string>): Promise<Response> {
    let dbOk = false;
    let aiOk = false;
    try {
      const dbTest = await env.DB.prepare('SELECT 1').first();
      dbOk = !!dbTest;
    } catch (e) {
      console.error('Health check: DB error', e);
    }
    try {
      const aiResp = await (env.AI as any).run?.(AI_MODEL_FAST, {
        messages: [{ role: 'user', content: 'Say "ok"' }],
        max_tokens: 10,
      });
      aiOk = !!aiResp;
    } catch (e) {
      console.error('Health check: AI error', e);
    }

    return jsonResponse(corsHeaders, {
      status: dbOk ? 'healthy' : 'degraded',
      environment: env.ENVIRONMENT,
        model: AI_MODEL_FAST,
      services: { ai: aiOk, database: dbOk, cache: true },
      timestamp: new Date().toISOString(),
    });
  },

  // ─── Generic Complete Handler (upgraded to 8B) ────────────────────────────

  async handleComplete(request: Request, env: Env, corsHeaders: Record<string, string>): Promise<Response> {
    let body: { prompt?: string; system?: string; max_tokens?: number; temperature?: number };
    try {
      body = await request.json();
    } catch {
      return jsonResponse(corsHeaders, { error: 'Invalid JSON body' }, 400);
    }
    if (!body.prompt || typeof body.prompt !== 'string' || body.prompt.length > 16000) {
      return jsonResponse(corsHeaders, { error: 'prompt must be a non-empty string (max 16KB)' }, 400);
    }

    const aiBinding = env.AI || (env as any).ai;
    try {
      const aiResponse = await (aiBinding as any).run?.(AI_MODEL_SMART, {
        messages: [
          { role: 'system', content: body.system || 'You are a helpful cloud infrastructure and cost optimization assistant. Always respond with valid JSON.' },
          { role: 'user', content: body.prompt },
        ],
        max_tokens: body.max_tokens || 2048,
        temperature: body.temperature ?? 0.3,
      });

      if (!aiResponse) {
        return jsonResponse(corsHeaders, { error: 'AI returned empty response' }, 502);
      }
      return jsonResponse(corsHeaders, { success: true, response: aiResponse.response });
    } catch (e) {
      console.error('Completion AI call failed', e);
      return jsonResponse(corsHeaders, { error: 'AI service unavailable' }, 502);
    }
  },

  // ─── Prompt Builders ──────────────────────────────────────────────────────

  buildAnalysisPrompt(req: AnalysisRequest): string {
    const fileTypeLabel = req.file_type === 'terraform' ? 'Terraform' :
                          req.file_type === 'cloudformation' ? 'CloudFormation' :
                          req.file_type === 'kubernetes' ? 'Kubernetes' : 'Docker Compose';
    const focus = req.options?.focus || 'all';
    const provider = req.options?.provider || 'aws';
    let code = req.content || '';
    if (code.length > 6000) code = code.slice(0, 6000) + '\n\n[Code truncated for analysis]';

    return `Analyze this ${fileTypeLabel} code for ${provider} cloud.

Focus areas: ${focus}

Return JSON with this exact structure:
{
  "resources": [{ "id": "type.name", "type": "aws_vpc", "name": "resource_name", "category": "networking", "config": {}, "estimated_cost": 0, "free_tier_eligible": true, "security_concerns": [] }],
  "connections": [{ "source": "source_id", "target": "target_id", "type": "depends_on", "valid": true, "description": "VPC used by subnet" }],
  "issues": [{ "severity": "high", "category": "security", "resource": "resource_name", "message": "Issue description", "explanation": "Why this is a problem", "fix": "How to fix it", "fix_example": "code example" }],
  "suggestions": [{ "type": "cost", "priority": 1, "title": "Suggestion title", "description": "What to do", "impact": "Expected benefit", "implementation": "How to implement" }],
  "cost_estimate": { "monthly_total": 0, "breakdown": {}, "optimization_potential": 0, "recommendations": [] },
  "security_score": 0,
  "compliance_status": { "score": 0, "violations": [], "recommendations": [] }
}

Code to analyze:
${code}`;
  },

  buildValidationPrompt(req: AnalysisRequest): string {
    let code = req.content || '';
    if (code.length > 6000) code = code.slice(0, 6000) + '\n\n[Code truncated]';
    return `Validate this infrastructure code for security and compliance.

Check for:
1. Open security groups (0.0.0.0/0)
2. Publicly accessible databases
3. Missing encryption
4. Overly permissive IAM
5. Missing logging/monitoring
6. Compliance with CIS AWS Foundations Benchmark

Return JSON with:
{
  "security_score": 0-100,
  "issues": [{ "severity": "critical|high|medium|low", "category": "security|compliance|best_practice", "resource": "resource_name", "message": "Issue description", "explanation": "Why this matters", "fix": "How to fix", "fix_example": "code example", "cis_control": "CIS control number" }],
  "compliance_status": { "score": 0-100, "violations": [], "recommendations": [] }
}

Code:
${code}`;
  },

  // ─── Response Parsers ─────────────────────────────────────────────────────

  parseAIResponse(aiResponse: any, req: AnalysisRequest): AnalysisResult {
    try {
      const responseText = aiResponse.response || '';
      const jsonMatch = responseText.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        const parsed = JSON.parse(jsonMatch[0]);
        return {
          success: true, type: 'analysis',
          summary: `Analyzed ${req.file_type} code with ${parsed.resources?.length || 0} resources`,
          resources: parsed.resources || [],
          connections: parsed.connections || [],
          issues: parsed.issues || [],
          suggestions: parsed.suggestions || [],
          cost_estimate: parsed.cost_estimate,
          security_score: parsed.security_score,
          compliance_status: parsed.compliance_status,
        };
      }
    } catch (e) {
      console.error('Failed to parse AI response:', e);
    }
    return { success: true, type: 'analysis', summary: 'Analysis completed with basic parsing', resources: [], connections: [], issues: [], suggestions: [] };
  },

  parseValidationResponse(aiResponse: any, _req: AnalysisRequest): AnalysisResult {
    try {
      const responseText = aiResponse.response || '';
      const jsonMatch = responseText.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        const parsed = JSON.parse(jsonMatch[0]);
        return {
          success: true, type: 'validation',
          summary: `Security score: ${parsed.security_score || 0}/100`,
          resources: [], connections: [],
          issues: parsed.issues || [],
          suggestions: [],
          security_score: parsed.security_score,
          compliance_status: parsed.compliance_status,
        };
      }
    } catch (e) {
      console.error('Failed to parse validation response:', e);
    }
    return { success: true, type: 'validation', summary: 'Validation completed', resources: [], connections: [], issues: [], suggestions: [] };
  },

  // ─── Helpers ──────────────────────────────────────────────────────────────

  async hashContent(content: string): Promise<string> {
    const encoder = new TextEncoder();
    const data = encoder.encode(content);
    const hashBuffer = await crypto.subtle.digest('SHA-256', data);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('').slice(0, 16);
  },
};

// ─── Utility ────────────────────────────────────────────────────────────────

function jsonResponse(headers: Record<string, string>, body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...headers, 'Content-Type': 'application/json' },
  });
}
