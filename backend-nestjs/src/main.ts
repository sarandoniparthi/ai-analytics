import { Logger, ValidationPipe } from '@nestjs/common';
import { NestFactory } from '@nestjs/core';
import { randomUUID } from 'crypto';
import { Request, Response } from 'express';

import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  const logger = new Logger('HTTP');

  app.use((req: Request, res: Response, next: () => void) => {
    const correlationId = req.header('x-correlation-id') || randomUUID();
    req.headers['x-correlation-id'] = correlationId;
    res.setHeader('x-correlation-id', correlationId);

    const started = Date.now();
    res.on('finish', () => {
      const durationMs = Date.now() - started;
      logger.log(
        `${req.method} ${req.originalUrl} ${res.statusCode} ${durationMs}ms correlation_id=${correlationId}`,
      );
    });
    next();
  });

  app.useGlobalPipes(
    new ValidationPipe({
      whitelist: true,
      forbidNonWhitelisted: true,
      transform: true,
    }),
  );

  const port = Number(process.env.PORT || 3000);
  await app.listen(port, '0.0.0.0');
  logger.log(`Listening on port ${port}`);
}

void bootstrap();
