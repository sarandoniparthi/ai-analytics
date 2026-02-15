import { Injectable } from '@nestjs/common';

@Injectable()
export class ResultStoreService {
  private readonly results = new Map<string, any>();

  set(conversationId: string, payload: any) {
    this.results.set(conversationId, payload);
  }

  get(conversationId: string) {
    return this.results.get(conversationId);
  }
}
