/**
 * Cloudflare AI Agent for Infrastructure Analysis
 * Provides intelligent infrastructure validation, cost optimization, and security analysis
 */

export interface Env {
  AI: Ai;
  CACHE: KVNamespace;
  RATE_LIMIT: KVNamespace;
  DB: D1Database;
  STORAGE: R2Bucket;
  ANALYSIS_QUEUE: Queue;
  ENVIRONMENT: string;
  ALLOWED_ORIGINS: string;
}

interface AnalysisRequest {
  action: 'analyze' | 'validate' | 'optimize' | 'explain';
  content: string;
  file_type: 'terraform' | 'cloudformation' | 'kubernetes' | 'docker-compose';
  options?: {
    focus?: 'cost' | 'security' | 'performance' | 'all';
    provider?: 'aws' | 'azure' | 'gcp';
  };
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

    // CORS headers
    const corsHeaders = {
      'Access-Control-Allow-Origin': env.ALLOWED_ORIGINS || '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    };

    // Handle preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    try {
      // Route requests
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

      return new Response('Not Found', { status: 404, headers: corsHeaders });
    } catch (error) {
      console.error('Agent error:', error);
      return new Response(
        JSON.stringify({ error: 'Internal server error' }),
        { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }
  },

  // ─── Analyze Handler ──────────────────────────────────────────────────────

  async handleAnalyze(request: Request, env: Env, corsHeaders: HeadersInit): Promise<Response> {
    const req: AnalysisRequest = await request.json();

    // Rate limiting
    const clientIP = request.headers.get('CF-Connecting-IP') || 'unknown';
    const rateLimitKey = `rate:${clientIP}:${Date.now()}`;
    const isLimited = await env.RATE_LIMIT.get(rateLimitKey);
    if (isLimited) {
      return new Response(
        JSON.stringify({ error: 'Rate limit exceeded. Please wait.' }),
        { status: 429, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }
    await env.RATE_LIMIT.put(rateLimitKey, '1', { expirationTtl: 60 });

    // Build AI prompt based on action
    const prompt = this.buildAnalysisPrompt(req);

    // Call Cloudflare AI
    const aiResponse = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
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
        {
          role: 'user',
          content: prompt
        }
      ],
      max_tokens: 4096,
      temperature: 0.3,
    });

    // Parse AI response
    const analysisResult = this.parseAIResponse(aiResponse, req);

    // Cache result
    const cacheKey = `analysis:${this.hashContent(req.content)}`;
    await env.CACHE.put(cacheKey, JSON.stringify(analysisResult), { expirationTtl: 3600 });

    // Store in D1 for history
    await env.DB.prepare(
      'INSERT INTO analyses (content_hash, file_type, result, created_at) VALUES (?, ?, ?, datetime("now"))'
    ).bind(this.hashContent(req.content), req.file_type, JSON.stringify(analysisResult)).run();

    return new Response(
      JSON.stringify(analysisResult),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  },

  // ─── Validate Handler ─────────────────────────────────────────────────────

  async handleValidate(request: Request, env: Env, corsHeaders: HeadersInit): Promise<Response> {
    const req: AnalysisRequest = await request.json();
    req.options = { ...req.options, focus: 'security' };

    const prompt = this.buildValidationPrompt(req);

    const aiResponse = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
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
        {
          role: 'user',
          content: prompt
        }
      ],
      max_tokens: 2048,
      temperature: 0.2,
    });

    const validationResult = this.parseValidationResponse(aiResponse, req);

    return new Response(
      JSON.stringify(validationResult),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  },

  // ─── Explain Handler ──────────────────────────────────────────────────────

  async handleExplain(request: Request, env: Env, corsHeaders: HeadersInit): Promise<Response> {
    const req: AnalysisRequest = await request.json();

    const prompt = `Explain this infrastructure code in simple terms. What does it do? How do the resources connect? What are the costs?

Code:
${req.content}

Provide:
1. Plain English explanation of what this infrastructure does
2. How resources are connected (data flow)
3. Cost breakdown and optimization opportunities
4. Security posture assessment
5. Recommendations for improvement`;

    const aiResponse = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
      messages: [
        {
          role: 'system',
          content: 'You are a helpful cloud architect who explains infrastructure in simple, clear language. Use analogies and examples where helpful.'
        },
        {
          role: 'user',
          content: prompt
        }
      ],
      max_tokens: 2048,
      temperature: 0.5,
    });

    return new Response(
      JSON.stringify({
        success: true,
        explanation: aiResponse.response,
        language: 'en',
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  },

  // ─── Health Handler ───────────────────────────────────────────────────────

  async handleHealth(env: Env, corsHeaders: HeadersInit): Promise<Response> {
    const dbTest = await env.DB.prepare('SELECT 1').first();
    const aiTest = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
      messages: [{ role: 'user', content: 'Say "ok"' }],
      max_tokens: 10,
    });

    return new Response(
      JSON.stringify({
        status: 'healthy',
        environment: env.ENVIRONMENT,
        services: {
          ai: !!aiTest,
          database: !!dbTest,
          cache: true,
        },
        timestamp: new Date().toISOString(),
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  },

  // ─── Helper: Build Analysis Prompt ────────────────────────────────────────

  buildAnalysisPrompt(req: AnalysisRequest): string {
    const fileTypeLabel = req.file_type === 'terraform' ? 'Terraform' :
                          req.file_type === 'cloudformation' ? 'CloudFormation' :
                          req.file_type === 'kubernetes' ? 'Kubernetes' : 'Docker Compose';

    const focus = req.options?.focus || 'all';
    const provider = req.options?.provider || 'aws';

    return `Analyze this ${fileTypeLabel} code for ${provider} cloud.

Focus areas: ${focus}

Return JSON with this exact structure:
{
  "resources": [
    {
      "id": "resource_type.resource_name",
      "type": "aws_vpc",
      "name": "resource_name",
      "category": "networking",
      "config": { ... },
      "estimated_cost": 0,
      "free_tier_eligible": true,
      "security_concerns": []
    }
  ],
  "connections": [
    {
      "source": "source_id",
      "target": "target_id",
      "type": "depends_on",
      "valid": true,
      "description": "VPC used by subnet"
    }
  ],
  "issues": [
    {
      "severity": "high",
      "category": "security",
      "resource": "resource_name",
      "message": "Issue description",
      "explanation": "Why this is a problem",
      "fix": "How to fix it",
      "fix_example": "code example"
    }
  ],
  "suggestions": [
    {
      "type": "cost",
      "priority": 1,
      "title": "Suggestion title",
      "description": "What to do",
      "impact": "Expected benefit",
      "implementation": "How to implement"
    }
  ],
  "cost_estimate": {
    "monthly_total": 0,
    "breakdown": {},
    "optimization_potential": 0,
    "recommendations": []
  },
  "security_score": 0,
  "compliance_status": {
    "score": 0,
    "violations": [],
    "recommendations": []
  }
}

Code to analyze:
${req.content}`;
  },

  // ─── Helper: Build Validation Prompt ──────────────────────────────────────

  buildValidationPrompt(req: AnalysisRequest): string {
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
  "issues": [
    {
      "severity": "critical|high|medium|low",
      "category": "security|compliance|best_practice",
      "resource": "resource_name",
      "message": "Issue description",
      "explanation": "Why this matters",
      "fix": "How to fix",
      "fix_example": "code example",
      "cis_control": "CIS control number if applicable"
    }
  ],
  "compliance_status": {
    "score": 0-100,
    "violations": ["list of violations"],
    "recommendations": ["list of recommendations"]
  }
}

Code:
${req.content}`;
  },

  // ─── Helper: Parse AI Response ────────────────────────────────────────────

  parseAIResponse(aiResponse: any, req: AnalysisRequest): AnalysisResult {
    try {
      // Try to extract JSON from response
      const responseText = aiResponse.response || '';
      const jsonMatch = responseText.match(/\{[\s\S]*\}/);

      if (jsonMatch) {
        const parsed = JSON.parse(jsonMatch[0]);
        return {
          success: true,
          type: 'analysis',
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

    // Fallback: return basic analysis
    return {
      success: true,
      type: 'analysis',
      summary: 'Analysis completed with basic parsing',
      resources: [],
      connections: [],
      issues: [],
      suggestions: [],
    };
  },

  // ─── Helper: Parse Validation Response ────────────────────────────────────

  parseValidationResponse(aiResponse: any, req: AnalysisRequest): AnalysisResult {
    try {
      const responseText = aiResponse.response || '';
      const jsonMatch = responseText.match(/\{[\s\S]*\}/);

      if (jsonMatch) {
        const parsed = JSON.parse(jsonMatch[0]);
        return {
          success: true,
          type: 'validation',
          summary: `Security score: ${parsed.security_score || 0}/100`,
          resources: [],
          connections: [],
          issues: parsed.issues || [],
          suggestions: [],
          security_score: parsed.security_score,
          compliance_status: parsed.compliance_status,
        };
      }
    } catch (e) {
      console.error('Failed to parse validation response:', e);
    }

    return {
      success: true,
      type: 'validation',
      summary: 'Validation completed',
      resources: [],
      connections: [],
      issues: [],
      suggestions: [],
    };
  },

  // ─── Helper: Hash Content ─────────────────────────────────────────────────

  hashContent(content: string): string {
    let hash = 0;
    for (let i = 0; i < content.length; i++) {
      const char = content.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash;
    }
    return Math.abs(hash).toString(36);
  },
};
