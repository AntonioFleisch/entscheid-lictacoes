import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function middleware(request: NextRequest) {
  const path = request.nextUrl.pathname;
  
  if (path.startsWith('/login') || path.startsWith('/api') || path.startsWith('/_next') || path === '/favicon.ico') {
      return NextResponse.next();
  }
  
  const token = request.cookies.get('refresh_token');
  if (!token) {
      return NextResponse.redirect(new URL('/login', request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico).*)'],
};
