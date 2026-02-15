import { Type } from 'class-transformer';
import { IsIn, IsInt, IsNotEmpty, IsOptional, IsString, IsUUID } from 'class-validator';

export class ChatRequestDto {
  @IsString()
  @IsNotEmpty()
  question!: string;

  @IsOptional()
  @IsString()
  @IsNotEmpty()
  @IsIn(['admin', 'store_manager', 'marketing', 'finance'])
  role?: string;

  @IsOptional()
  @Type(() => Number)
  @IsInt()
  store_id?: number;

  @IsOptional()
  @IsUUID()
  conversation_id?: string;

  @IsOptional()
  @IsString()
  org_id?: string;

  @IsOptional()
  @IsString()
  user_id?: string;
}
