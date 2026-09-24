import { routes, type VercelConfig } from '@vercel/config/v1'

const rawOrigin = (process.env.ZENDOC_ORIGIN_URL || '').trim()

if (!rawOrigin) {
  throw new Error(
    'ZENDOC_ORIGIN_URL is required. Set it to the reviewed HTTPS OCI origin before deploying.',
  )
}

const parsedOrigin = new URL(rawOrigin)

if (
  parsedOrigin.protocol !== 'https:' ||
  parsedOrigin.username ||
  parsedOrigin.password ||
  parsedOrigin.search ||
  parsedOrigin.hash
) {
  throw new Error(
    'ZENDOC_ORIGIN_URL must be a credential-free HTTPS origin without query or fragment.',
  )
}

const origin = parsedOrigin.origin

export const config: VercelConfig = {
  git: {
    deploymentEnabled: false,
  },
  rewrites: [routes.rewrite('/:path*', `${origin}/:path*`)],
  headers: [
    routes.header('/:path*', [
      {
        key: 'x-vercel-enable-rewrite-caching',
        value: '0',
      },
    ]),
  ],
}
