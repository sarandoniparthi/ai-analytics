import { HttpModule } from '@nestjs/axios';
import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';

import { AuthController } from './auth.controller';
import { AuthService } from './auth.service';
import { ChatController } from './chat.controller';
import { ChatService } from './chat.service';
import { ResultStoreService } from './result-store.service';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
    }),
    HttpModule.register({
      timeout: Number(process.env.AGNO_TIMEOUT_MS || 45000),
      maxRedirects: 0,
    }),
  ],
  controllers: [AuthController, ChatController],
  providers: [AuthService, ChatService, ResultStoreService],
})
export class AppModule {}
