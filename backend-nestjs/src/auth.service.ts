import { Injectable, InternalServerErrorException, UnauthorizedException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import * as jwt from 'jsonwebtoken';
import { Pool } from 'pg';

import { LoginDto } from './auth.dto';

type AuthUser = {
  user_id: string;
  username: string;
  role: 'admin' | 'store_manager' | 'marketing' | 'finance';
  store_ids: number[];
  is_all_stores: boolean;
  org_id: string;
};

@Injectable()
export class AuthService {
  private readonly pool: Pool;

  constructor(private readonly configService: ConfigService) {
    this.pool = new Pool({
      host: this.configService.get<string>('POSTGRES_HOST', 'postgres'),
      port: Number(this.configService.get<string>('POSTGRES_PORT', '5432')),
      database: this.configService.get<string>('POSTGRES_DB', 'pagila'),
      user: this.configService.get<string>('POSTGRES_USER', 'postgres'),
      password: this.configService.get<string>('POSTGRES_PASSWORD', 'postgres'),
    });
  }

  async login(payload: LoginDto) {
    const user = await this.validateUser(payload.username, payload.password);
    const secret = this.configService.get<string>('JWT_SECRET', '');
    if (!secret) {
      throw new InternalServerErrorException('JWT_SECRET is not configured.');
    }
    const token = jwt.sign(
      {
        user_id: user.user_id,
        role: user.role,
        store_ids: user.store_ids,
        is_all_stores: user.is_all_stores,
        org_id: user.org_id,
      },
      secret,
      { expiresIn: '8h', subject: user.user_id },
    );

    return {
      token,
      user,
    };
  }

  private async validateUser(username: string, password: string): Promise<AuthUser> {
    const client = await this.pool.connect();
    try {
      const userResult = await client.query<{
        id: number;
        username: string;
        role: 'admin' | 'store_manager' | 'marketing' | 'finance';
        is_all_stores: boolean;
      }>(
        `
        SELECT id, username, role, is_all_stores
        FROM app_users
        WHERE username = $1
          AND is_active = TRUE
          AND password_hash = crypt($2, password_hash)
        LIMIT 1
        `,
        [username, password],
      );

      const row = userResult.rows[0];
      if (!row) {
        throw new UnauthorizedException('Invalid username or password.');
      }

      let storeIds: number[] = [];
      if (!row.is_all_stores) {
        const storeResult = await client.query<{ store_id: number }>(
          `
          SELECT store_id
          FROM app_user_store_access
          WHERE user_id = $1
          ORDER BY store_id
          `,
          [row.id],
        );
        storeIds = storeResult.rows.map((r) => Number(r.store_id)).filter((n) => Number.isFinite(n));
      }

      return {
        user_id: String(row.id),
        username: row.username,
        role: row.role,
        store_ids: storeIds,
        is_all_stores: row.is_all_stores,
        org_id: 'default-org',
      };
    } finally {
      client.release();
    }
  }
}
