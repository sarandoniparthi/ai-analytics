import { Body, Controller, Post, Req } from '@nestjs/common';
import { Request } from 'express';

import { ChatRequestDto } from './chat.dto';
import { ChatService } from './chat.service';

@Controller('api')
export class ChatController {
  constructor(private readonly chatService: ChatService) {}

  @Post('ask')
  async ask(@Body() body: ChatRequestDto, @Req() req: Request) {
    const correlationId = req.header('x-correlation-id') || '';
    const authorization = req.header('authorization') || '';
    return this.chatService.forwardToAgno(body, correlationId, authorization);
  }
}
