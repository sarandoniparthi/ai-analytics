import { HttpService } from '@nestjs/axios';
import {
  BadRequestException,
  ForbiddenException,
  HttpException,
  Injectable,
  InternalServerErrorException,
  UnauthorizedException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { AxiosError } from 'axios';
import * as jwt from 'jsonwebtoken';
import { JwtPayload } from 'jsonwebtoken';
import { firstValueFrom } from 'rxjs';
import { v4 as uuidv4 } from 'uuid';

import { ChatRequestDto } from './chat.dto';
import { ResultStoreService } from './result-store.service';

type UserContext = {
  role: string;
  store_id: number;
  allowed_views: string[];
};

type JwtContext = {
  role?: string;
  store_id?: number;
  store_ids?: number[];
  is_all_stores?: boolean;
  org_id?: string;
  user_id?: string;
};

@Injectable()
export class ChatService {
  constructor(
    private readonly httpService: HttpService,
    private readonly configService: ConfigService,
    private readonly resultStore: ResultStoreService,
  ) {}

  async forwardToAgno(body: ChatRequestDto, correlationId: string, authorizationHeader: string) {
    const agnoBaseUrl = this.configService.get<string>('AGNO_URL', 'http://agno-python:8000');
    const internalToken = this.configService.get<string>('INTERNAL_TOKEN', '');
    if (!internalToken) {
      throw new InternalServerErrorException('INTERNAL_TOKEN is not configured.');
    }

    const jwtContext = this.extractContextFromJwt(authorizationHeader);
    const role = jwtContext.role || body.role;
    if (!role) {
      throw new BadRequestException('role is required (from JWT or request body).');
    }
    if (!['admin', 'store_manager', 'marketing', 'finance'].includes(role)) {
      throw new BadRequestException('Invalid role in JWT/body.');
    }
    const requestedStoreId = body.store_id ?? 0;
    const storeId = this.resolveStoreId(role, requestedStoreId, jwtContext);

    const userContext: UserContext = {
      role,
      store_id: storeId,
      allowed_views: this.getAllowedViews(role),
    };

    const conversationId = body.conversation_id || uuidv4();
    const requestBody = {
      conversation_id: conversationId,
      question: body.question,
      org_id: jwtContext.org_id || body.org_id || 'default-org',
      user_id: jwtContext.user_id || body.user_id || 'default-user',
      user_context: userContext,
    };

    try {
      const response = await this.postWithSingleRetry(
        `${agnoBaseUrl}/run`,
        requestBody,
        {
          'X-Internal-Token': internalToken,
          'x-correlation-id': correlationId,
        },
      );
      const payload = { ...response, conversation_id: conversationId };
      this.resultStore.set(conversationId, payload);
      return payload;
    } catch (error) {
      const axiosError = error as AxiosError<{ detail?: string }>;
      if (axiosError.response) {
        const status = axiosError.response.status || 502;
        const detail = axiosError.response.data?.detail || 'Agno service error.';
        throw new HttpException({ detail }, status);
      }
      if (axiosError.code === 'ECONNABORTED') {
        throw new HttpException({ detail: 'Agno service timeout.' }, 504);
      }
      throw new HttpException({ detail: 'Failed to reach Agno service.' }, 502);
    }
  }

  private getAllowedViews(role: string): string[] {
    switch (role) {
      case 'admin':
        return ['v_payment_scoped', 'v_customer_masked', 'v_rental_scoped'];
      case 'store_manager':
        return ['v_payment_scoped', 'v_rental_scoped'];
      case 'marketing':
        return ['v_customer_masked'];
      case 'finance':
        return ['v_payment_scoped'];
      default:
        return [];
    }
  }

  private async postWithSingleRetry(url: string, body: unknown, headers: Record<string, string>) {
    try {
      const response = await firstValueFrom(this.httpService.post(url, body, { headers }));
      return response.data;
    } catch (error) {
      const axiosError = error as AxiosError;
      const retryable =
        axiosError.code === 'ECONNABORTED' ||
        axiosError.code === 'ECONNRESET' ||
        axiosError.code === 'ENOTFOUND' ||
        !axiosError.response ||
        (axiosError.response.status >= 500 && axiosError.response.status <= 599);
      if (!retryable) {
        throw error;
      }
      const response = await firstValueFrom(this.httpService.post(url, body, { headers }));
      return response.data;
    }
  }

  private extractContextFromJwt(authorizationHeader: string): JwtContext {
    if (!authorizationHeader) {
      return {};
    }
    const match = authorizationHeader.match(/^Bearer\s+(.+)$/i);
    if (!match) {
      throw new UnauthorizedException('Invalid Authorization header format.');
    }
    const token = match[1].trim();
    const secret = this.configService.get<string>('JWT_SECRET', '');
    if (!secret) {
      throw new InternalServerErrorException('JWT_SECRET is not configured.');
    }
    try {
      const decoded = jwt.verify(token, secret) as JwtPayload & Record<string, unknown>;
      return {
        role: this.toStringClaim(decoded.role),
        store_id: this.toNumberClaim(decoded.store_id),
        store_ids: this.toNumberArrayClaim(decoded.store_ids),
        is_all_stores: this.toBooleanClaim(decoded.is_all_stores),
        org_id: this.toStringClaim(decoded.org_id),
        user_id: this.toStringClaim(decoded.user_id) || this.toStringClaim(decoded.sub),
      };
    } catch {
      throw new UnauthorizedException('Invalid JWT token.');
    }
  }

  private toStringClaim(value: unknown): string | undefined {
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
    return undefined;
  }

  private toNumberClaim(value: unknown): number | undefined {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value;
    }
    if (typeof value === 'string') {
      const parsed = Number(value);
      if (Number.isFinite(parsed)) {
        return parsed;
      }
    }
    return undefined;
  }

  private toNumberArrayClaim(value: unknown): number[] | undefined {
    if (!Array.isArray(value)) {
      return undefined;
    }
    const numbers = value
      .map((item) => (typeof item === 'number' ? item : Number(item)))
      .filter((item) => Number.isFinite(item));
    return numbers.length ? numbers : [];
  }

  private toBooleanClaim(value: unknown): boolean | undefined {
    if (typeof value === 'boolean') {
      return value;
    }
    if (typeof value === 'string') {
      if (value.toLowerCase() === 'true') return true;
      if (value.toLowerCase() === 'false') return false;
    }
    return undefined;
  }

  private resolveStoreId(role: string, requestedStoreId: number, jwtContext: JwtContext): number {
    const hasJwtScope = Boolean(jwtContext.role || jwtContext.user_id || jwtContext.store_ids);
    if (!hasJwtScope) {
      const fallbackStore = jwtContext.store_id ?? requestedStoreId ?? 0;
      if ((role === 'store_manager' || role === 'marketing' || role === 'finance') && fallbackStore <= 0) {
        throw new BadRequestException('store_id is required for this role.');
      }
      return fallbackStore;
    }

    const isAllStores = jwtContext.is_all_stores === true;
    if (isAllStores || role === 'admin') {
      return requestedStoreId > 0 ? requestedStoreId : jwtContext.store_id ?? 0;
    }

    const allowedStoreIds = jwtContext.store_ids || [];
    if (!allowedStoreIds.length) {
      throw new ForbiddenException('No store access configured for this user.');
    }
    if (requestedStoreId > 0 && !allowedStoreIds.includes(requestedStoreId)) {
      throw new ForbiddenException('Requested store is outside your access scope.');
    }
    return requestedStoreId > 0 ? requestedStoreId : allowedStoreIds[0];
  }
}
