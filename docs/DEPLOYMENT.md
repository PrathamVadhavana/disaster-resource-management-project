# Deployment Guide

This guide covers deploying the Disaster Management System to production.

## Table of Contents

1. [Pre-deployment Checklist](#pre-deployment-checklist)
2. [Frontend Deployment (Vercel)](#frontend-deployment)
3. [Backend Deployment (Railway/Fly.io)](#backend-deployment)
4. [Database Setup (Supabase)](#database-setup)
5. [Environment Configuration](#environment-configuration)
6. [CI/CD Pipeline](#cicd-pipeline)
7. [Monitoring & Maintenance](#monitoring)

## Pre-deployment Checklist

- [ ] All environment variables configured
- [ ] Database schema applied
- [ ] ML models trained and saved
- [ ] Security review completed
- [ ] Performance testing done
- [ ] Backup strategy in place
- [ ] Domain names configured
- [ ] SSL certificates ready

## Frontend Deployment

### Vercel Deployment

1. **Install Vercel CLI**
   ```bash
   npm i -g vercel
   ```

2. **Login to Vercel**
   ```bash
   vercel login
   ```

3. **Deploy**
   ```bash
   cd frontend
   vercel --prod
   ```

4. **Configure Environment Variables**
   - Go to Vercel Dashboard > Your Project > Settings > Environment Variables
   - Add all variables from `.env.example`
   - Important variables:
     - `NEXT_PUBLIC_SUPABASE_URL`
     - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
     - `NEXT_PUBLIC_API_URL` (your backend URL)

5. **Custom Domain**
   - Add custom domain in Vercel Dashboard
   - Configure DNS records as instructed
   - SSL is automatically provisioned

### Alternative: Netlify

```bash
# Install Netlify CLI
npm i -g netlify-cli

# Login
netlify login

# Deploy
cd frontend
netlify deploy --prod
```

## Backend Deployment

### Railway Deployment

1. **Install Railway CLI**
   ```bash
   npm i -g @railway/cli
   ```

2. **Login and Initialize**
   ```bash
   railway login
   railway init
   ```

3. **Configure**
   ```bash
   # Add environment variables
   railway variables set SUPABASE_URL=your-url
   railway variables set SUPABASE_SERVICE_KEY=your-key
   # ... add all other variables
   ```

4. **Deploy**
   ```bash
   cd backend
   railway up
   ```

5. **Generate Domain**
   ```bash
   railway domain
   ```

### Alternative: Fly.io Deployment

1. **Install Fly CLI**
   ```bash
   curl -L https://fly.io/install.sh | sh
   ```

2. **Login**
   ```bash
   flyctl auth login
   ```

3. **Launch Application**
   ```bash
   cd backend
   flyctl launch
   ```

4. **Set Secrets**
   ```bash
   flyctl secrets set SUPABASE_URL=your-url
   flyctl secrets set SUPABASE_SERVICE_KEY=your-key
   # ... add all other secrets
   ```

5. **Deploy**
   ```bash
   flyctl deploy
   ```

### Docker Deployment

For self-hosted deployment:

```bash
# Build images
docker-compose build

# Run in production mode
docker-compose -f docker-compose.prod.yml up -d

# View logs
docker-compose logs -f
```

## Database Setup

### Supabase Configuration

1. **Create Project**
   - Go to [supabase.com](https://supabase.com)
   - Create new project
   - Wait for provisioning

2. **Apply Schema**
   - Open SQL Editor
   - Copy contents of `database/schema.sql`
   - Execute the SQL

3. **Configure Authentication**
   - Enable email authentication
   - Configure email templates
   - Set up OAuth providers (optional)

4. **Enable Realtime**
   - Go to Database > Replication
   - Enable realtime for tables:
     - disasters
     - resources
     - predictions

5. **Configure Storage** (if using file uploads)
   - Create storage buckets
   - Set up RLS policies

6. **Get Credentials**
   - Settings > API
   - Copy:
     - Project URL
     - Anon/Public key
     - Service role key (keep secret!)
     - Database password

### Backup Configuration

```sql
-- Setup automated backups
-- In Supabase Dashboard > Database > Backups
-- Enable Point-in-Time Recovery (PITR)
```

## Environment Configuration

### Production Environment Variables

Create production `.env` files with real values:

**Frontend (.env.production)**
```env
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-production-anon-key
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
NEXT_PUBLIC_MAPBOX_TOKEN=your-mapbox-token
NODE_ENV=production
```

**Backend (.env.production)**
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-production-service-key
DATABASE_URL=postgresql+asyncpg://...
ALLOWED_ORIGINS=https://yourdomain.com
DEBUG=false
SECRET_KEY=your-secure-random-key
LOG_LEVEL=WARNING
```

## CI/CD Pipeline

### GitHub Actions Setup

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Production

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '20'
      
      - name: Install frontend dependencies
        run: |
          cd frontend
          npm ci
      
      - name: Run frontend tests
        run: |
          cd frontend
          npm test
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install backend dependencies
        run: |
          cd backend
          pip install -r requirements.txt
      
      - name: Run backend tests
        run: |
          cd backend
          pytest

  deploy-frontend:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: amondnet/vercel-action@v25
        with:
          vercel-token: ${{ secrets.VERCEL_TOKEN }}
          vercel-org-id: ${{ secrets.VERCEL_ORG_ID }}
          vercel-project-id: ${{ secrets.VERCEL_PROJECT_ID }}
          vercel-args: '--prod'

  deploy-backend:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: railwayapp/railway-deploy@v1
        with:
          railway-token: ${{ secrets.RAILWAY_TOKEN }}
          service: backend
```

## Monitoring

### Application Monitoring

1. **Sentry Integration**
   ```bash
   # Frontend
   npm install --save @sentry/nextjs
   
   # Backend
   pip install sentry-sdk[fastapi]
   ```

2. **Configure Sentry**
   ```javascript
   // frontend/sentry.config.js
   import * as Sentry from "@sentry/nextjs";
   
   Sentry.init({
     dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
     environment: process.env.NODE_ENV,
   });
   ```

3. **Health Checks**
   - Frontend: `/api/health`
   - Backend: `/health`
   - Database: Supabase Dashboard

### Performance Monitoring

1. **Vercel Analytics**
   ```bash
   npm install @vercel/analytics
   ```

2. **Supabase Logs**
   - Access via Dashboard > Logs
   - Set up log retention
   - Configure alerts

3. **Custom Metrics**
   - API response times
   - ML model inference times
   - Database query performance
   - Resource allocation efficiency

## Security Hardening

### Production Checklist

- [ ] Enable HTTPS only
- [ ] Configure CORS properly
- [ ] Set secure headers
- [ ] Enable rate limiting
- [ ] Implement WAF rules
- [ ] Regular security audits
- [ ] Dependency updates
- [ ] Secret rotation schedule

### Environment Security

```bash
# Use secrets manager
# Never commit .env files
# Rotate keys regularly
# Use principle of least privilege
```

## Scaling Considerations

### Auto-scaling Configuration

**Vercel**: Auto-scales by default

**Railway/Fly.io**: Configure in `fly.toml` or Railway dashboard

```toml
# fly.toml
[services]
  [[services.scale]]
    min = 1
    max = 10
```

### Database Optimization

- Enable connection pooling
- Set up read replicas
- Implement caching (Redis)
- Optimize queries with indexes
- Regular VACUUM operations

## Maintenance

### Regular Tasks

**Daily**
- Monitor error rates
- Check system health
- Review logs

**Weekly**
- Review performance metrics
- Update dependencies
- Database maintenance
- Backup verification

**Monthly**
- Security audit
- Cost optimization review
- Capacity planning
- ML model retraining

### Backup & Recovery

```bash
# Database backup
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d).sql

# Restore
psql $DATABASE_URL < backup_20240101.sql
```

## Rollback Procedure

1. **Vercel Rollback**
   ```bash
   vercel rollback
   ```

2. **Railway Rollback**
   ```bash
   railway rollback
   ```

3. **Database Rollback**
   - Use Supabase PITR (Point-in-Time Recovery)
   - Or restore from backup

## Support & Troubleshooting

### Common Issues

**Frontend not connecting to backend**
- Check CORS configuration
- Verify API URL in environment variables
- Check network policies

**Authentication failures**
- Verify Supabase credentials
- Check JWT token expiration
- Review RLS policies

**ML predictions failing**
- Check model files exist
- Verify feature inputs
- Review model version compatibility

### Getting Help

- Check logs: `railway logs` or `flyctl logs`
- Vercel dashboard for frontend logs
- Supabase dashboard for database logs
- GitHub Issues for bug reports

---

**Deployment completed? Don't forget to:**
1. Update DNS records
2. Test all functionality
3. Monitor for 24-48 hours
4. Document any issues
5. Celebrate! 🎉
